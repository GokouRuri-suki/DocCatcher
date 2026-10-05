/**
 * 主应用逻辑
 */

// 全局状态
const state = {
    currentDocument: null,
    documents: [],
    currentTab: 'upload'
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadDocuments();
    initUploadArea();
});

// 导航切换
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = item.dataset.tab;
            switchTab(tab);
        });
    });
}

function switchTab(tabName) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.tab === tabName);
    });

    // 更新内容区域
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });

    state.currentTab = tabName;

    // 切换标签时的特殊处理
    if (tabName === 'knowledge' || tabName === 'plan' || tabName === 'quiz' || tabName === 'qa') {
        refreshDocumentSelects();
    }
}

// 显示/隐藏加载遮罩
function showLoading(text = '处理中...') {
    const overlay = document.getElementById('loadingOverlay');
    overlay.querySelector('.loading-text').textContent = text;
    overlay.style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// 显示提示消息
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 加载文档列表
async function loadDocuments() {
    try {
        state.documents = await api.getDocuments();
        renderDocumentList();
        refreshDocumentSelects();
    } catch (error) {
        showToast('加载文档列表失败: ' + error.message, 'error');
    }
}

// 渲染文档列表
function renderDocumentList() {
    const container = document.getElementById('documentList');
    
    if (state.documents.length === 0) {
        container.innerHTML = '<p class="empty-state">暂无文档，请上传 PDF 文件</p>';
        return;
    }

    container.innerHTML = state.documents.map(doc => `
        <div class="doc-card" data-id="${doc.id}">
            <div class="doc-card-header">
                <span class="doc-card-title">${escapeHtml(doc.original_name)}</span>
                <div class="doc-card-actions">
                    <button class="btn btn-danger btn-sm" onclick="deleteDocument(${doc.id})">删除</button>
                </div>
            </div>
            <div class="doc-card-info">
                <span class="doc-status ${doc.status}">${getStatusText(doc.status)}</span>
                <span>📄 ${doc.total_pages} 页</span>
                <span>📦 ${formatFileSize(doc.file_size)}</span>
            </div>
        </div>
    `).join('');

    // 为文档卡片添加点击事件
    container.querySelectorAll('.doc-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') return;
            const docId = parseInt(card.dataset.id);
            selectDocument(docId);
        });
    });
}

// 选择文档
function selectDocument(docId) {
    const doc = state.documents.find(d => d.id === docId);
    if (!doc) return;
    
    state.currentDocument = doc;
    showToast(`已选择文档: ${doc.original_name}`, 'info');
    
    // 更新所有下拉框的选中值
    document.querySelectorAll('select[id$="DocSelect"]').forEach(select => {
        select.value = docId;
    });
}

// 删除文档
async function deleteDocument(docId) {
    if (!confirm('确定要删除这个文档吗？')) return;
    
    try {
        await api.deleteDocument(docId);
        showToast('删除成功', 'success');
        loadDocuments();
    } catch (error) {
        showToast('删除失败: ' + error.message, 'error');
    }
}

// 刷新文档下拉框
function refreshDocumentSelects() {
    const selects = ['knowledgeDocSelect', 'planDocSelect', 'quizDocSelect', 'qaDocSelect'];
    
    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;
        
        const currentValue = select.value;
        select.innerHTML = '<option value="">选择文档</option>' +
            state.documents
                .filter(d => d.status === 'processed')
                .map(d => `<option value="${d.id}">${escapeHtml(d.original_name)}</option>`)
                .join('');
        
        if (currentValue) {
            select.value = currentValue;
        } else if (state.currentDocument) {
            select.value = state.currentDocument.id;
        }
    });
}

// 初始化上传区域
function initUploadArea() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');

    // 拖拽事件
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // 点击选择文件
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
            e.target.value = '';
        }
    });

    // 点击上传区域
    uploadArea.addEventListener('click', (e) => {
        if (e.target.tagName !== 'BUTTON') {
            fileInput.click();
        }
    });
}

// 处理文件上传
async function handleFileUpload(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('请选择 PDF 文件', 'error');
        return;
    }

    const progressDiv = document.getElementById('uploadProgress');
    const progressFill = progressDiv.querySelector('.progress-fill');
    const progressText = progressDiv.querySelector('.progress-text');
    
    progressDiv.style.display = 'block';
    progressText.textContent = `正在上传: ${file.name}`;

    try {
        const doc = await api.uploadDocument(file, (percent) => {
            progressFill.style.width = `${percent}%`;
            progressText.textContent = `正在上传: ${Math.round(percent)}%`;
        });

        progressText.textContent = '上传完成，正在解析...';
        showToast('上传成功！', 'success');
        
        // 刷新文档列表
        await loadDocuments();

        // 文件已上传完毕，收起上传进度条
        progressDiv.style.display = 'none';
        progressFill.style.width = '0%';

        // 展示真实的解析进度（按页计数）
        if (doc && doc.id) {
            ProgressBar.show('parseProgressHost', 'parse');
            ProgressBar.startPolling('parse', doc.id, {
                containerId: 'parseProgressHost',
                onComplete: (payload) => {
                    showToast(payload.message || '解析完成', 'success');
                    setTimeout(() => ProgressBar.hide('parseProgressHost'), 1500);
                    loadDocuments();
                },
                onFail: (payload) => {
                    showToast(payload.message || '解析失败', 'error');
                    // 失败后多停留一会儿，方便用户看清错误信息
                    setTimeout(() => ProgressBar.hide('parseProgressHost'), 4000);
                    loadDocuments();
                }
            });
        }
    } catch (error) {
        showToast('上传失败: ' + error.message, 'error');
        progressDiv.style.display = 'none';
    }
}

// 定时刷新文档状态
let statusRefreshInterval = null;

function startStatusRefresh() {
    if (statusRefreshInterval) return;
    
    statusRefreshInterval = setInterval(async () => {
        const docs = await api.getDocuments();
        const hasProcessing = docs.some(d => d.status === 'uploading' || d.status === 'parsing');
        
        state.documents = docs;
        renderDocumentList();
        refreshDocumentSelects();
        
        if (!hasProcessing) {
            clearInterval(statusRefreshInterval);
            statusRefreshInterval = null;
        }
    }, 3000);
}

// 工具函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getStatusText(status) {
    const statusMap = {
        'uploading': '上传中',
        'parsing': '解析中',
        'processed': '已处理',
        'error': '错误'
    };
    return statusMap[status] || status;
}
