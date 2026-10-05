/**
 * 知识体系模块
 *
 * 进度完全交给统一的 ProgressBar 组件：
 * 可计数阶段显示真实百分比，AI 调用阶段显示不确定动画（不编造百分比）。
 */

document.addEventListener('DOMContentLoaded', () => {
    // 生成知识点按钮
    const generateBtn = document.getElementById('generateKnowledgeBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', handleGenerateKnowledge);
    }

    // 视图切换
    document.querySelectorAll('.view-toggle .toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const view = btn.dataset.view;
            document.getElementById('mindmapView').style.display = view === 'mindmap' ? 'block' : 'none';
            document.getElementById('graphView').style.display = view === 'graph' ? 'block' : 'none';

            if (view === 'graph') {
                // 图谱在隐藏状态下宽度为 0，必须等切过来之后再渲染/重绘
                onGraphViewShown();
            }
        });
    });
});

async function handleGenerateKnowledge() {
    const docSelect = document.getElementById('knowledgeDocSelect');
    const docId = docSelect.value;
    
    if (!docId) {
        showToast('请先选择文档', 'error');
        return;
    }

    const maxChunksInput = document.getElementById('knowledgeMaxChunks');
    const maxChunks = parseInt(maxChunksInput && maxChunksInput.value) || 20;

    // 先在界面上展示进度条（真实进度由后端轮询填充）
    ProgressBar.show('knowledgeProgressHost', 'knowledge');

    try {
        await api.generateKnowledge(docId, maxChunks);

        ProgressBar.startPolling('knowledge', docId, {
            containerId: 'knowledgeProgressHost',
            onComplete: (payload) => {
                showToast(payload.message || '知识点生成完成！', 'success');
                // 稍作停留让用户看到 100%，再隐藏并加载数据
                setTimeout(() => {
                    ProgressBar.hide('knowledgeProgressHost');
                    loadKnowledgeData(docId);
                }, 900);
            },
            onFail: (payload) => {
                showToast(payload.message || '生成失败', 'error');
                setTimeout(() => ProgressBar.hide('knowledgeProgressHost'), 4000);
            }
        });
    } catch (error) {
        ProgressBar.hide('knowledgeProgressHost');
        showToast(error.message, 'error');
    }
}

async function loadKnowledgeData(docId) {
    try {
        // 并行加载树形结构和图谱数据
        const [tree, graph] = await Promise.all([
            api.getKnowledgeTree(docId),
            api.getKnowledgeGraph(docId)
        ]);

        if (tree.length === 0) {
            showToast('暂无知识点数据，请先生成', 'info');
            return;
        }

        // 渲染思维导图
        renderMindMap(tree);
        
        // 渲染知识图谱
        renderKnowledgeGraph(graph);
    } catch (error) {
        showToast('加载知识体系失败: ' + error.message, 'error');
    }
}

// 监听文档选择变化
document.getElementById('knowledgeDocSelect')?.addEventListener('change', (e) => {
    const docId = e.target.value;
    if (docId) {
        loadKnowledgeData(docId);
    }
});

// 详情请求序号：快速连续点多个节点时，只有最后一次点击的结果能落地
let detailRequestSeq = 0;

/**
 * 打开知识点详情面板
 *
 * 注意：/knowledge/tree 与 /knowledge/graph 为控制响应体积都**不返回 content**，
 * 所以这里必须按 id 再拉一次 /documents/knowledge/{id} 才能显示正文。
 */
async function showKnowledgeDetail(point) {
    const panel = document.getElementById('knowledgeDetail');
    const titleEl = document.getElementById('detailTitle');
    const descEl = document.getElementById('detailDescription');
    const contentEl = document.getElementById('detailContent');
    const pagesEl = document.getElementById('detailPages');

    if (!point || point.id === undefined) return;

    const seq = ++detailRequestSeq;

    // 先用已有信息立即渲染，避免面板空白等待
    // 描述与正文都是 AI 生成的 Markdown，走 MD.render（含消毒与降级）
    titleEl.textContent = point.title || '';
    descEl.innerHTML = MD.render(point.description || '');
    pagesEl.textContent = point.page_numbers ? `📖 相关页码: ${point.page_numbers}` : '';
    contentEl.innerHTML = MD.render(point.content || '') || '正在加载正文…';
    panel.style.display = 'block';

    try {
        const full = await api.getKnowledgePoint(point.id);

        // 期间用户又点了别的节点，或已关闭面板 -> 丢弃这次结果
        if (seq !== detailRequestSeq || panel.style.display === 'none') return;

        titleEl.textContent = full.title || point.title || '';
        descEl.innerHTML = MD.render(full.description || '');
        pagesEl.textContent = full.page_numbers ? `📖 相关页码: ${full.page_numbers}` : '';
        contentEl.innerHTML = MD.render(full.content || '') || '（该知识点没有更详细的正文）';
    } catch (error) {
        if (seq !== detailRequestSeq) return;
        console.error('加载知识点详情失败:', error);
        contentEl.innerHTML = MD.render('（正文加载失败，请重试）');
    }
}

function closeDetail() {
    detailRequestSeq++;   // 让在途请求作废
    document.getElementById('knowledgeDetail').style.display = 'none';
}
