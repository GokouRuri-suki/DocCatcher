/**
 * 学习规划模块
 */

document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generatePlanBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', handleGeneratePlan);
    }
});

async function handleGeneratePlan() {
    const docSelect = document.getElementById('planDocSelect');
    const docId = docSelect.value;
    const days = parseInt(document.getElementById('planDays').value) || 30;
    
    if (!docId) {
        showToast('请先选择文档', 'error');
        return;
    }

    ProgressBar.show('planProgressHost', 'study_plan');
    
    try {
        await api.generateStudyPlan(docId, days, null);

        ProgressBar.startPolling('study_plan', docId, {
            containerId: 'planProgressHost',
            onComplete: (payload) => {
                showToast(payload.message || '学习规划生成完成！', 'success');
                setTimeout(() => {
                    ProgressBar.hide('planProgressHost');
                    loadStudyPlans(docId);
                }, 900);
            },
            onFail: (payload) => {
                showToast(payload.message || '生成失败', 'error');
                setTimeout(() => ProgressBar.hide('planProgressHost'), 4000);
            }
        });
    } catch (error) {
        ProgressBar.hide('planProgressHost');
        showToast(error.message, 'error');
    }
}

async function loadStudyPlans(docId) {
    try {
        const plans = await api.getStudyPlans(docId);
        
        if (plans.length === 0) {
            document.getElementById('planList').innerHTML = '<p class="empty-state">暂无学习规划，请先生成</p>';
            return;
        }

        // 加载第一个规划的详情
        const planDetail = await api.getStudyPlanDetail(plans[0].id);
        renderStudyPlan(planDetail);
    } catch (error) {
        showToast('加载学习规划失败: ' + error.message, 'error');
    }
}

function renderStudyPlan(plan) {
    const container = document.getElementById('planList');
    
    if (!plan.items || plan.items.length === 0) {
        container.innerHTML = '<p class="empty-state">暂无学习项目</p>';
        return;
    }

    container.innerHTML = `
        <h3 style="margin-bottom: 16px;">${escapeHtml(plan.title)}</h3>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">${escapeHtml(plan.description || '')}</p>
        ${plan.items.map(item => `
            <div class="plan-day">
                <div class="plan-day-header ${item.completed ? 'completed' : ''}" onclick="togglePlanDay(this)">
                    <span class="plan-day-title">第 ${item.day_number} 天: ${escapeHtml(item.title)}</span>
                    <span>${item.completed ? '✅ 已完成' : '⬜ 未完成'}</span>
                </div>
                <div class="plan-day-content show">
                    <p class="plan-tasks">${escapeHtml(item.tasks || '暂无任务描述')}</p>
                    <label class="plan-checkbox">
                        <input type="checkbox" ${item.completed ? 'checked' : ''} 
                               onchange="togglePlanItem(${item.id}, this.checked)">
                        <span>标记为已完成</span>
                    </label>
                </div>
            </div>
        `).join('')}
    `;
}

function togglePlanDay(header) {
    const content = header.nextElementSibling;
    content.classList.toggle('show');
}

async function togglePlanItem(itemId, completed) {
    try {
        await api.updatePlanItem(itemId, completed);
        showToast(completed ? '已标记为完成' : '已取消完成标记', 'success');
        
        // 更新 UI
        const header = event.target.closest('.plan-day').querySelector('.plan-day-header');
        header.classList.toggle('completed', completed);
        header.querySelector('span:last-child').textContent = completed ? '✅ 已完成' : '⬜ 未完成';
    } catch (error) {
        showToast('更新失败: ' + error.message, 'error');
    }
}

// 监听文档选择变化
document.getElementById('planDocSelect')?.addEventListener('change', (e) => {
    const docId = e.target.value;
    if (docId) {
        loadStudyPlans(docId);
    }
});
