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

function showKnowledgeDetail(point) {
    const panel = document.getElementById('knowledgeDetail');
    document.getElementById('detailTitle').textContent = point.title;
    document.getElementById('detailDescription').textContent = point.description || '';
    document.getElementById('detailContent').textContent = point.content || '';
    document.getElementById('detailPages').textContent = point.page_numbers ? `📖 相关页码: ${point.page_numbers}` : '';
    panel.style.display = 'block';
}

function closeDetail() {
    document.getElementById('knowledgeDetail').style.display = 'none';
}
