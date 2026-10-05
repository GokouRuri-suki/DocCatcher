/**
 * 智能问答模块
 */

document.addEventListener('DOMContentLoaded', () => {
    const askBtn = document.getElementById('askQuestionBtn');
    if (askBtn) {
        askBtn.addEventListener('click', handleAskQuestion);
    }

    // Enter 键发送
    const input = document.getElementById('qaInput');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAskQuestion();
            }
        });
    }
});

async function handleAskQuestion() {
    const docSelect = document.getElementById('qaDocSelect');
    const docId = docSelect.value;
    const input = document.getElementById('qaInput');
    const question = input.value.trim();
    
    if (!docId) {
        showToast('请先选择文档', 'error');
        return;
    }
    
    if (!question) {
        showToast('请输入问题', 'error');
        return;
    }

    // 显示用户问题
    addQAMessage('user', question);
    input.value = '';

    // 显示加载状态
    const loadingId = addQAMessage('assistant', '正在思考...', true);

    try {
        const result = await api.askQuestion(docId, question);
        
        // 移除加载消息
        document.getElementById(loadingId)?.remove();
        
        // 显示回答
        addQAMessage('assistant', result.answer, false, result.sources);
    } catch (error) {
        document.getElementById(loadingId)?.remove();
        addQAMessage('assistant', '抱歉，回答您的问题遇到了困难: ' + error.message);
    }
}

function addQAMessage(role, content, isLoading = false, sources = null) {
    const history = document.getElementById('qaHistory');
    
    // 移除空状态
    const emptyState = history.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const messageId = 'qa-msg-' + Date.now();
    const avatar = role === 'user' ? '👤' : '🤖';
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `qa-message ${role}`;
    messageDiv.id = messageId;
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        sourcesHtml = `
            <div class="qa-sources">
                📖 参考来源:
                ${sources.map(s => `<span>第${s.page_start}-${s.page_end}页 ${s.section || ''}</span>`).join('')}
            </div>
        `;
    }
    
    // AI 的回答按 Markdown 渲染（marked + DOMPurify，见 markdown.js）；
    // 用户自己发的消息保持纯文本转义 —— 渲染用户输入只有坏处没有好处
    const isAssistant = role === 'assistant';
    let bodyHtml;
    if (isLoading) {
        bodyHtml = '<span class="loading-dots">...</span>';
    } else if (isAssistant) {
        bodyHtml = MD.render(content);
    } else {
        bodyHtml = escapeHtml(content).replace(/\n/g, '<br>');
    }

    messageDiv.innerHTML = `
        <div class="qa-avatar">${avatar}</div>
        <div class="qa-bubble ${isAssistant ? 'md-body' : ''}">
            ${bodyHtml}
            ${sourcesHtml}
        </div>
    `;
    
    history.appendChild(messageDiv);
    history.scrollTop = history.scrollHeight;
    
    return messageId;
}

// 监听文档选择变化
document.getElementById('qaDocSelect')?.addEventListener('change', (e) => {
    const docId = e.target.value;
    const history = document.getElementById('qaHistory');
    
    if (docId) {
        history.innerHTML = `
            <div class="empty-state">
                <p>💡 已选择文档，请输入你的问题</p>
                <p>系统将根据 PDF 内容为你解答</p>
            </div>
        `;
    } else {
        history.innerHTML = `
            <div class="empty-state">
                <p>💡 选择文档后，输入你的问题</p>
                <p>系统将根据 PDF 内容为你解答</p>
            </div>
        `;
    }
});
