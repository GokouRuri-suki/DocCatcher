#!/usr/bin/env node
/**
 * 知识图谱配置回归校验
 *
 * 背景：曾出现「知识图谱看不清字」的 bug —— vis.js 的 shape:'dot' 会把标签
 * 画在圆点【外面】，而字体又被设成白色，导致白字落在浅色背景上完全隐形。
 * 本脚本把真实的图谱数据喂进 visualization.js 的构造函数，断言最终交给
 * vis.js 的配置是可读的。
 *
 * 用法：
 *   node frontend/scripts/verify_viz.js                      # 自动从本地服务取数据
 *   node frontend/scripts/verify_viz.js path/to/graph.json    # 用现成的 JSON
 *   node frontend/scripts/verify_viz.js http://host/api/...   # 指定接口
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const VIZ_FILE = path.join(REPO_ROOT, 'frontend', 'js', 'visualization.js');
const DEFAULT_URL = 'http://localhost:8000/api/documents/1/knowledge/graph';

async function loadGraphData(arg) {
    if (arg && fs.existsSync(arg)) {
        return JSON.parse(fs.readFileSync(arg, 'utf8'));
    }
    const url = arg || DEFAULT_URL;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`取图谱数据失败: HTTP ${res.status} (${url})`);
    return res.json();
}

/** 相对亮度与对比度（WCAG） */
function luminance(hex) {
    const c = hex.replace('#', '');
    const v = [0, 2, 4]
        .map(i => parseInt(c.substr(i, 2), 16) / 255)
        .map(x => (x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)));
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function contrast(a, b) {
    const l1 = luminance(a), l2 = luminance(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

(async () => {
    const data = await loadGraphData(process.argv[2]);

    // 最小桩：只为把 visualization.js 里的纯函数加载出来
    const sandbox = {
        window: { addEventListener() {}, innerHeight: 900 },
        document: { getElementById() { return null; }, createElement() { return {}; } },
        d3: {}, vis: {},
        requestAnimationFrame: (f) => f(),
        setTimeout, clearTimeout, console,
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(VIZ_FILE, 'utf8'), sandbox);

    const nodes = sandbox.buildGraphNodes(data);
    const edges = sandbox.buildGraphEdges(data);
    const options = sandbox.buildGraphOptions();

    let pass = 0, fail = 0;
    const check = (name, ok, detail) => {
        console.log(`  ${ok ? '✓' : '✗'} ${name}${detail ? '  — ' + detail : ''}`);
        ok ? pass++ : fail++;
    };

    console.log(`数据: ${nodes.length} 节点 / ${edges.length} 边\n`);

    check("shape 全为 'box'（标签在框内）", nodes.every(n => n.shape === 'box'));
    check('字体全为白色', nodes.every(n => String(n.font.color).toLowerCase() === '#ffffff'));

    if (nodes.length) {
        const worst = nodes.reduce((a, b) =>
            contrast(a.font.color, a.color.background) < contrast(b.font.color, b.color.background) ? a : b);
        const minC = contrast(worst.font.color, worst.color.background);
        check('白字对比度达标（WCAG AA ≥ 4.5:1）', minC >= 4.5,
            `最低 ${minC.toFixed(2)}:1 (${worst.color.background})`);
    }

    check('标签未被截断', nodes.every(n => !/[.…]{3}$/.test(n.label)));
    check('长标签可换行（widthConstraint）', nodes.every(n => n.widthConstraint && n.widthConstraint.maximum > 0));
    check('悬浮提示含完整标题', nodes.every(n => n.title && n.title.length > 0));
    check('节点有内边距（margin）', nodes.every(n => n.margin && n.margin.left > 0));

    check('物理稳定化已配置并自适应',
        options.physics.stabilization.iterations >= 200 && options.physics.stabilization.fit === true);
    check('开启导航按钮', options.interaction.navigationButtons === true);
    check('开启键盘操作', !!(options.interaction.keyboard && options.interaction.keyboard.enabled));

    // 边样式逻辑（用合成数据，避免依赖真实文档里恰好有哪种关系）
    const synth = sandbox.buildGraphEdges({
        edges: [
            { source_id: 1, target_id: 2, relation_type: 'related' },
            { source_id: 1, target_id: 3, relation_type: 'prerequisite' },
            { source_id: 1, target_id: 4, relation_type: 'contains' },
        ],
    });
    check('related 边为双向箭头', synth[0].arrows.to.enabled && synth[0].arrows.from.enabled);
    check('prerequisite 边为单向', synth[1].arrows.to.enabled && !synth[1].arrows.from.enabled);
    check('contains 边为单向', synth[2].arrows.to.enabled && !synth[2].arrows.from.enabled);
    check('related 边为虚线', synth[0].dashes === true);

    console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
    process.exit(fail ? 1 : 0);
})().catch(err => {
    console.error('校验失败:', err.message);
    process.exit(1);
});
