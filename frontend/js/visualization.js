/**
 * 可视化模块 - 思维导图（D3）和知识图谱（vis.js）
 *
 * 知识图谱可读性要点（历史 bug 修复）：
 * 1. vis.js 里 shape:'dot' 会把标签画在【圆点外面】，之前又设了白色字体，
 *    导致白字落在浅色背景上完全看不见。改为 shape:'box'（标签在框内）+ 白字。
 * 2. 容器 #graphView 初始 display:none，宽度为 0 时初始化 vis 会得到零宽画布，
 *    因此改为"可见时才渲染"，并在每次切换到图谱视图时 redraw + fit。
 * 3. 稳定后关闭物理引擎，节点不再漂移抖动。
 * 4. 长标题用 widthConstraint 自动换行，不再粗暴截断成 12 个字符。
 */

let mindMapSvg = null;
let knowledgeGraphNetwork = null;
let lastGraphData = null;
let graphRendered = false;
let graphResizeTimer = null;

// 各层级节点的配色
// 全部为深色，保证白字对比度达到 WCAG AA（>= 4.5:1）：
//   #1e40af -> 8.72:1   #4f46e5 -> 6.29:1   #7c3aed -> 5.70:1
const LEVEL_STYLE = {
    1: { background: '#1e40af', fontSize: 14 },
    2: { background: '#4f46e5', fontSize: 13 },
    3: { background: '#7c3aed', fontSize: 12 }
};
const LEVEL_FALLBACK = { background: '#7c3aed', fontSize: 12 };

// 关系类型对应的边样式与图例文案
const EDGE_STYLE = {
    prerequisite: { color: '#ef4444', dashes: false, arrows: 'to', label: '前置' },
    related: { color: '#94a3b8', dashes: true, arrows: 'to, from', label: '相关' },
    contains: { color: '#10b981', dashes: false, arrows: 'to', label: '包含' }
};

/**
 * 渲染思维导图 (使用 D3.js)
 */
function renderMindMap(treeData) {
    if (typeof d3 === 'undefined') {
        showVisualizationError('mindmapView', '思维导图库（D3.js）加载失败，请检查网络或改用本地依赖');
        return;
    }

    const svg = d3.select('#mindmapSvg');
    svg.selectAll('*').remove();

    const container = document.getElementById('mindmapView');
    const width = Math.max(container.clientWidth - 40, 320);
    const height = 600;

    svg.attr('width', width).attr('height', height);

    // 创建根节点
    const root = {
        name: '知识体系',
        children: treeData
    };

    // 创建树形布局
    const treeLayout = d3.tree().size([height - 100, width - 200]);
    const rootD3 = d3.hierarchy(root);
    treeLayout(rootD3);

    // 创建 SVG 组
    const g = svg.append('g')
        .attr('transform', 'translate(100, 50)');

    // 绘制连线
    g.selectAll('.link')
        .data(rootD3.links())
        .enter()
        .append('path')
        .attr('class', 'link')
        .attr('fill', 'none')
        .attr('stroke', '#cbd5e1')
        .attr('stroke-width', 2)
        .attr('d', d3.linkHorizontal()
            .x(d => d.y)
            .y(d => d.x));

    // 绘制节点
    const nodes = g.selectAll('.node')
        .data(rootD3.descendants())
        .enter()
        .append('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.y}, ${d.x})`)
        .style('cursor', 'pointer')
        .on('click', (event, d) => {
            if (d.data.id) {
                showKnowledgeDetail(d.data);
            }
        });

    // 悬浮显示完整标题（标题被截断时的补偿）
    nodes.append('title')
        .text(d => d.data.title || d.data.name || '');

    // 节点圆形
    nodes.append('circle')
        .attr('r', d => d.depth === 0 ? 12 : d.depth === 1 ? 10 : 8)
        .attr('fill', d => {
            if (d.depth === 0) return '#1e40af';
            if (d.depth === 1) return '#4f46e5';
            return '#7c3aed';
        })
        .attr('stroke', '#fff')
        .attr('stroke-width', 2);

    // 节点文本
    nodes.append('text')
        .attr('dy', '0.35em')
        .attr('x', d => d.children ? -15 : 15)
        .attr('text-anchor', d => d.children ? 'end' : 'start')
        .text(d => {
            const name = d.data.title || d.data.name;
            return name.length > 18 ? name.substring(0, 18) + '…' : name;
        })
        .style('font-size', d => d.depth === 0 ? '14px' : d.depth === 1 ? '12px' : '11px')
        .style('fill', '#1e293b')
        .style('font-weight', d => d.depth <= 1 ? '600' : '400');

    // 添加缩放和拖拽
    const zoom = d3.zoom()
        .scaleExtent([0.5, 2])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);
}

/** 在容器内显示一条错误提示（依赖加载失败等） */
function showVisualizationError(containerId, message) {
    const container = document.getElementById(containerId);
    if (!container) return;
    let box = container.querySelector('.viz-error');
    if (!box) {
        box = document.createElement('div');
        box.className = 'viz-error';
        container.appendChild(box);
    }
    box.textContent = message;
    box.style.display = 'block';
}

/* ------------------------------------------------------------------ */
/* 知识图谱                                                            */
/* ------------------------------------------------------------------ */

function buildGraphNodes(graphData) {
    return graphData.nodes.map(node => {
        const style = LEVEL_STYLE[node.level] || LEVEL_FALLBACK;
        const title = node.title || '(未命名)';

        return {
            id: node.id,
            label: title,             // 完整标题，靠 widthConstraint 自动换行
            title: title,             // hover 提示
            level: node.level,
            shape: 'box',             // 标签画在框内 -> 文字可读
            margin: { top: 8, bottom: 8, left: 12, right: 12 },
            widthConstraint: { maximum: 170 },
            shapeProperties: { borderRadius: 8 },
            borderWidth: 2,
            color: {
                background: style.background,
                border: 'rgba(255,255,255,0.85)',
                highlight: { background: '#f59e0b', border: '#ffffff' },
                hover: { background: style.background, border: '#f59e0b' }
            },
            font: {
                color: '#ffffff',     // 白字落在深色框内，对比度足够
                size: style.fontSize,
                face: 'Noto Sans, Microsoft YaHei, PingFang SC, sans-serif',
                strokeWidth: 0,
                align: 'center'
            }
        };
    });
}

function buildGraphEdges(graphData) {
    return graphData.edges.map(edge => {
        const style = EDGE_STYLE[edge.relation_type] || EDGE_STYLE.related;
        return {
            from: edge.source_id,
            to: edge.target_id,
            title: edge.description || style.label,
            color: { color: style.color, highlight: '#f59e0b' },
            dashes: style.dashes,
            arrows: {
                to: { enabled: style.arrows.indexOf('to') !== -1 },
                from: { enabled: style.arrows.indexOf('from') !== -1 }
            },
            width: 2
        };
    });
}

function buildGraphOptions() {
    return {
        nodes: { shadow: { enabled: true, size: 6, x: 0, y: 2 } },
        edges: {
            smooth: { type: 'continuous' },
            selectionWidth: 2
        },
        physics: {
            enabled: true,
            barnesHut: {
                gravitationalConstant: -6000,
                springLength: 170,
                springConstant: 0.04,
                damping: 0.6,
                avoidOverlap: 0.35
            },
            stabilization: { enabled: true, iterations: 250, fit: true }
        },
        interaction: {
            hover: true,
            tooltipDelay: 150,
            navigationButtons: true,
            keyboard: { enabled: true, bindToWindow: false },
            zoomView: true,
            dragView: true
        },
        layout: { improvedLayout: true }
    };
}

/** 真正创建 vis 网络（仅当容器可见时调用） */
function buildGraph(container, graphData) {
    if (typeof vis === 'undefined') {
        showVisualizationError('knowledgeGraph', '图谱库（vis-network）加载失败，请检查网络或改用本地依赖');
        return false;
    }

    // 高度自适应，避免节点拥挤
    const viewportBudget = Math.max(window.innerHeight - 300, 420);
    container.style.height = Math.min(760, viewportBudget) + 'px';

    const nodes = new vis.DataSet(buildGraphNodes(graphData));
    const edges = new vis.DataSet(buildGraphEdges(graphData));

    if (knowledgeGraphNetwork) {
        knowledgeGraphNetwork.destroy();
        knowledgeGraphNetwork = null;
    }

    knowledgeGraphNetwork = new vis.Network(
        container, { nodes, edges }, buildGraphOptions()
    );

    // 稳定后关闭物理引擎，节点停住不动，文字才读得稳
    knowledgeGraphNetwork.once('stabilizationIterationsDone', () => {
        knowledgeGraphNetwork.setOptions({ physics: { enabled: false } });
    });

    knowledgeGraphNetwork.on('click', (params) => {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const nodeData = graphData.nodes.find(n => n.id === nodeId);
            if (nodeData) showKnowledgeDetail(nodeData);
        }
    });

    return true;
}

/**
 * 渲染知识图谱
 * 若容器当前不可见（display:none，宽度为 0），只记住数据，
 * 等切换到图谱视图时再由 onGraphViewShown() 真正渲染。
 */
function renderKnowledgeGraph(graphData) {
    lastGraphData = graphData;
    graphRendered = false;

    if (knowledgeGraphNetwork) {
        knowledgeGraphNetwork.destroy();
        knowledgeGraphNetwork = null;
    }

    tryRenderGraph();
}

/** 容器可见时才渲染 */
function tryRenderGraph() {
    if (graphRendered || !lastGraphData) return false;

    const container = document.getElementById('knowledgeGraph');
    if (!container) return false;

    // 隐藏时宽度为 0，此时初始化会得到零宽画布
    if (container.clientWidth === 0) return false;

    graphRendered = buildGraph(container, lastGraphData);
    return graphRendered;
}

/** 切换到图谱视图时调用：渲染或重绘并自适应 */
function onGraphViewShown() {
    if (!lastGraphData) return;

    const justRendered = tryRenderGraph();

    if (knowledgeGraphNetwork) {
        // 让布局引擎按新尺寸重新铺开
        requestAnimationFrame(() => {
            if (!knowledgeGraphNetwork) return;
            knowledgeGraphNetwork.redraw();
            if (!justRendered) knowledgeGraphNetwork.fit();
        });
    }
}

/** 窗口尺寸变化时重绘（防抖） */
window.addEventListener('resize', () => {
    if (graphResizeTimer) clearTimeout(graphResizeTimer);
    graphResizeTimer = setTimeout(() => {
        if (knowledgeGraphNetwork) knowledgeGraphNetwork.redraw();
    }, 200);
});
