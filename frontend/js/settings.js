/**
 * AI 设置模块
 */

// 预设配置
const PRESETS = {
    openai: {
        url: 'https://api.openai.com/v1',
        model: 'gpt-4o-mini'
    },
    deepseek: {
        url: 'https://api.deepseek.com/v1',
        model: 'deepseek-chat'
    },
    zhipu: {
        url: 'https://open.bigmodel.cn/api/paas/v4',
        model: 'glm-4-flash'
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // 设置按钮
    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openSettingsModal);
    }

    // 保存按钮
    const saveBtn = document.getElementById('saveSettingsBtn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveSettings);
    }

    // 测试连接按钮
    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.addEventListener('click', testConnection);
    }

    // 模型选择变化
    const modelSelect = document.getElementById('modelSelect');
    if (modelSelect) {
        modelSelect.addEventListener('change', () => {
            const customGroup = document.getElementById('customModelGroup');
            if (modelSelect.value === 'custom') {
                customGroup.style.display = 'block';
            } else {
                customGroup.style.display = 'none';
            }
        });
    }

    // 检查配置状态
    checkConfigStatus();
});

async function checkConfigStatus() {
    try {
        const status = await api.getConfigStatus();
        const settingsBtn = document.getElementById('settingsBtn');
        
        if (!status.is_configured) {
            settingsBtn.classList.add('not-configured');
            // 首次访问自动弹出设置
            setTimeout(() => {
                openSettingsModal();
                showToast('请先配置 AI API 以使用完整功能', 'info');
            }, 500);
        }
    } catch (error) {
        console.error('检查配置状态失败:', error);
    }
}

function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    modal.style.display = 'flex';
    
    // 加载当前配置
    loadCurrentConfig();
}

function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    modal.style.display = 'none';
}

async function loadCurrentConfig() {
    try {
        const config = await api.getConfig();
        
        document.getElementById('apiBaseUrl').value = config.api_base_url || '';
        
        // API Key 脱敏处理：如果包含 * 说明已配置，显示占位符
        const apiKeyInput = document.getElementById('apiKey');
        if (config.api_key && config.api_key.includes('*')) {
            apiKeyInput.value = '';
            apiKeyInput.placeholder = `已配置: ${config.api_key}（留空保持不变）`;
        } else {
            apiKeyInput.value = config.api_key || '';
            apiKeyInput.placeholder = '输入你的 API Key';
        }
        
        // 设置模型选择
        const modelSelect = document.getElementById('modelSelect');
        const customModel = document.getElementById('customModel');
        const customGroup = document.getElementById('customModelGroup');
        
        // 检查是否是预设模型
        const presetModels = ['gpt-4o-mini', 'gpt-4o', 'deepseek-chat', 'deepseek-reasoner', 'glm-4-flash'];
        if (presetModels.includes(config.model)) {
            modelSelect.value = config.model;
            customGroup.style.display = 'none';
        } else if (config.model) {
            modelSelect.value = 'custom';
            customModel.value = config.model;
            customGroup.style.display = 'block';
        }
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

async function saveSettings() {
    const apiBaseUrl = document.getElementById('apiBaseUrl').value.trim();
    let apiKey = document.getElementById('apiKey').value.trim();
    const modelSelect = document.getElementById('modelSelect');
    const customModel = document.getElementById('customModel').value.trim();
    
    let model = modelSelect.value;
    if (model === 'custom') {
        model = customModel;
    }
    
    if (!apiBaseUrl) {
        showToast('请输入 API 地址', 'error');
        return;
    }
    
    if (!model) {
        showToast('请选择或输入模型', 'error');
        return;
    }
    
    // 如果用户没有输入新的 Key，检查是否已配置
    if (!apiKey) {
        try {
            const status = await api.getConfigStatus();
            if (status.is_configured) {
                // 已配置，使用特殊标记保留原 Key
                apiKey = '__KEEP__';
            } else {
                // 未配置，要求用户输入
                showToast('请输入 API Key', 'error');
                return;
            }
        } catch (error) {
            console.error('检查配置状态失败:', error);
            showToast('请输入 API Key', 'error');
            return;
        }
    }
    
    try {
        await api.saveConfig(apiBaseUrl, apiKey, model);
        showToast('配置保存成功！', 'success');
        
        // 更新设置按钮状态
        const settingsBtn = document.getElementById('settingsBtn');
        settingsBtn.classList.remove('not-configured');
        
        closeSettingsModal();
    } catch (error) {
        showToast('保存失败: ' + error.message, 'error');
    }
}

function fillPreset(presetName) {
    const preset = PRESETS[presetName];
    if (!preset) return;
    
    document.getElementById('apiBaseUrl').value = preset.url;
    
    // 设置模型
    const modelSelect = document.getElementById('modelSelect');
    const customModel = document.getElementById('customModel');
    const customGroup = document.getElementById('customModelGroup');
    
    const presetModels = ['gpt-4o-mini', 'gpt-4o', 'deepseek-chat', 'deepseek-reasoner', 'glm-4-flash'];
    if (presetModels.includes(preset.model)) {
        modelSelect.value = preset.model;
        customGroup.style.display = 'none';
    } else {
        modelSelect.value = 'custom';
        customModel.value = preset.model;
        customGroup.style.display = 'block';
    }
    
    showToast(`已填入 ${presetName} 配置，请输入 API Key`, 'info');
}

async function testConnection() {
    const testBtn = document.getElementById('testConnectionBtn');
    const originalText = testBtn.textContent;
    
    try {
        testBtn.disabled = true;
        testBtn.textContent = '测试中...';
        
        const result = await api.testAIConnection();
        
        if (result.success) {
            showToast(`✅ ${result.message}`, 'success');
        } else {
            showToast(`❌ ${result.message}`, 'error');
        }
    } catch (error) {
        showToast(`❌ 测试失败: ${error.message}`, 'error');
    } finally {
        testBtn.disabled = false;
        testBtn.textContent = originalText;
    }
}

// 点击弹窗外部关闭
document.addEventListener('click', (e) => {
    const modal = document.getElementById('settingsModal');
    if (e.target === modal) {
        closeSettingsModal();
    }
});

// ESC 关闭弹窗
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('settingsModal');
        if (modal.style.display === 'flex') {
            closeSettingsModal();
        }
    }
});
