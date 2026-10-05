/**
 * 测试模块
 */

let currentQuiz = null;
let currentAttemptId = null;
let currentQuestionIndex = 0;
let userAnswers = {};

document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generateQuizBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', handleGenerateQuiz);
    }

    // 答题按钮
    document.getElementById('prevQuestionBtn')?.addEventListener('click', () => navigateQuestion(-1));
    document.getElementById('nextQuestionBtn')?.addEventListener('click', () => navigateQuestion(1));
    document.getElementById('submitQuizBtn')?.addEventListener('click', handleSubmitQuiz);
});

async function handleGenerateQuiz() {
    const docSelect = document.getElementById('quizDocSelect');
    const docId = docSelect.value;
    const count = parseInt(document.getElementById('quizCount').value) || 10;
    
    if (!docId) {
        showToast('请先选择文档', 'error');
        return;
    }

    ProgressBar.show('quizProgressHost', 'quiz');
    
    try {
        await api.generateQuiz(docId, count);

        ProgressBar.startPolling('quiz', docId, {
            containerId: 'quizProgressHost',
            onComplete: (payload) => {
                showToast(payload.message || '测验生成完成！', 'success');
                setTimeout(() => {
                    ProgressBar.hide('quizProgressHost');
                    loadQuizzes(docId);
                }, 900);
            },
            onFail: (payload) => {
                showToast(payload.message || '生成失败', 'error');
                setTimeout(() => ProgressBar.hide('quizProgressHost'), 4000);
            }
        });
    } catch (error) {
        ProgressBar.hide('quizProgressHost');
        showToast(error.message, 'error');
    }
}

async function loadQuizzes(docId) {
    try {
        const quizzes = await api.getQuizzes(docId);
        renderQuizList(quizzes);
    } catch (error) {
        showToast('加载测验列表失败: ' + error.message, 'error');
    }
}

function renderQuizList(quizzes) {
    const container = document.getElementById('quizList');
    
    if (quizzes.length === 0) {
        container.innerHTML = '<p class="empty-state">暂无测验，请先生成</p>';
        return;
    }

    container.innerHTML = quizzes.map(quiz => `
        <div class="quiz-card">
            <h4>${escapeHtml(quiz.title)}</h4>
            <p>共 ${quiz.question_count} 题</p>
            <button class="btn btn-primary" onclick="startQuiz(${quiz.id})">开始测验</button>
        </div>
    `).join('');
}

async function startQuiz(quizId) {
    try {
        // 获取测验详情
        currentQuiz = await api.getQuizDetail(quizId);
        
        // 开始测验
        const result = await api.startQuiz(quizId);
        currentAttemptId = result.attempt_id;
        
        // 初始化答题状态
        currentQuestionIndex = 0;
        userAnswers = {};
        
        // 显示答题界面
        document.getElementById('quizList').style.display = 'none';
        document.getElementById('quizArea').style.display = 'block';
        document.getElementById('quizResult').style.display = 'none';
        
        // 渲染第一题
        renderQuestion();
    } catch (error) {
        showToast('开始测验失败: ' + error.message, 'error');
    }
}

function renderQuestion() {
    const questions = currentQuiz.questions;
    const question = questions[currentQuestionIndex];
    
    // 更新进度
    document.getElementById('currentQuestion').textContent = currentQuestionIndex + 1;
    document.getElementById('totalQuestions').textContent = questions.length;
    document.getElementById('quizTitle').textContent = currentQuiz.title;
    
    // 题型显示
    const typeMap = {
        'single_choice': '单选题',
        'multiple_choice': '多选题',
        'true_false': '判断题',
        'fill_blank': '填空题'
    };
    document.getElementById('questionType').textContent = typeMap[question.question_type] || question.question_type;
    document.getElementById('questionText').textContent = question.question_text;
    
    // 渲染选项
    const optionsContainer = document.getElementById('questionOptions');
    const fillInput = document.getElementById('fillInput');
    
    if (question.question_type === 'fill_blank') {
        optionsContainer.style.display = 'none';
        fillInput.style.display = 'block';
        fillInput.value = userAnswers[question.id] || '';
    } else {
        optionsContainer.style.display = 'flex';
        fillInput.style.display = 'none';
        
        const isMultiple = question.question_type === 'multiple_choice';
        const currentAnswer = userAnswers[question.id] || (isMultiple ? [] : null);
        
        optionsContainer.innerHTML = Object.entries(question.options || {}).map(([key, value]) => {
            const isSelected = isMultiple 
                ? currentAnswer.includes(key)
                : currentAnswer === key;
            
            return `
                <label class="option-item ${isSelected ? 'selected' : ''}">
                    <input type="${isMultiple ? 'checkbox' : 'radio'}" 
                           name="question-${question.id}"
                           value="${key}"
                           ${isSelected ? 'checked' : ''}
                           onchange="selectAnswer('${key}', ${isMultiple})">
                    <span><strong>${key}.</strong> ${escapeHtml(value)}</span>
                </label>
            `;
        }).join('');
    }
    
    // 更新按钮状态
    document.getElementById('prevQuestionBtn').disabled = currentQuestionIndex === 0;
    document.getElementById('nextQuestionBtn').style.display = 
        currentQuestionIndex === questions.length - 1 ? 'none' : 'inline-flex';
    document.getElementById('submitQuizBtn').style.display = 
        currentQuestionIndex === questions.length - 1 ? 'inline-flex' : 'none';
}

function selectAnswer(value, isMultiple) {
    const question = currentQuiz.questions[currentQuestionIndex];
    
    if (isMultiple) {
        let current = userAnswers[question.id] || [];
        if (current.includes(value)) {
            current = current.filter(v => v !== value);
        } else {
            current.push(value);
        }
        userAnswers[question.id] = current;
    } else {
        userAnswers[question.id] = value;
    }
    
    // 更新 UI
    document.querySelectorAll('.option-item').forEach(item => {
        const input = item.querySelector('input');
        item.classList.toggle('selected', input.checked);
    });
}

function navigateQuestion(direction) {
    // 保存当前答案
    const question = currentQuiz.questions[currentQuestionIndex];
    if (question.question_type === 'fill_blank') {
        userAnswers[question.id] = document.getElementById('fillInput').value;
    }
    
    currentQuestionIndex += direction;
    currentQuestionIndex = Math.max(0, Math.min(currentQuestionIndex, currentQuiz.questions.length - 1));
    renderQuestion();
}

async function handleSubmitQuiz() {
    // 保存最后一题的答案
    const question = currentQuiz.questions[currentQuestionIndex];
    if (question.question_type === 'fill_blank') {
        userAnswers[question.id] = document.getElementById('fillInput').value;
    }
    
    if (!confirm('确定要提交答案吗？')) return;
    
    showLoading('正在提交...');
    
    try {
        // 构建答案列表
        const answers = currentQuiz.questions.map(q => ({
            question_id: q.id,
            answer: userAnswers[q.id] || null
        }));
        
        const result = await api.submitQuiz(currentAttemptId, answers);
        
        // 获取详细结果
        const detail = await api.getQuizResult(currentAttemptId);
        renderQuizResult(detail);
    } catch (error) {
        showToast('提交失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

function renderQuizResult(result) {
    document.getElementById('quizArea').style.display = 'none';
    document.getElementById('quizResult').style.display = 'block';
    
    // 显示分数
    document.getElementById('resultScore').textContent = Math.round(result.attempt.score);
    document.getElementById('correctCount').textContent = result.attempt.correct_count;
    document.getElementById('totalCount').textContent = result.attempt.total_questions;
    
    // 显示详细结果
    const detailsContainer = document.getElementById('resultDetails');
    detailsContainer.innerHTML = result.questions.map((q, index) => {
        const isCorrect = q.is_correct;
        const userAnswer = q.user_answer;
        const correctAnswer = q.correct_answer;
        
        let answerDisplay = '';
        if (q.question_type === 'fill_blank') {
            answerDisplay = `你的答案: ${userAnswer || '未作答'}`;
        } else if (q.question_type === 'multiple_choice') {
            const userAns = Array.isArray(userAnswer) ? userAnswer.join(', ') : '未作答';
            const correctAns = Array.isArray(correctAnswer) ? correctAnswer.join(', ') : correctAnswer;
            answerDisplay = `你的答案: ${userAns} | 正确答案: ${correctAns}`;
        } else {
            answerDisplay = `你的答案: ${userAnswer || '未作答'} | 正确答案: ${correctAnswer}`;
        }
        
        return `
            <div class="result-question ${isCorrect ? 'correct' : 'incorrect'}">
                <div class="result-question-header">
                    <strong>第 ${index + 1} 题</strong>
                    <span class="result-badge ${isCorrect ? 'correct' : 'incorrect'}">
                        ${isCorrect ? '✓ 正确' : '✗ 错误'}
                    </span>
                </div>
                <p>${escapeHtml(q.question_text)}</p>
                <p class="result-answer">${answerDisplay}</p>
                ${q.explanation ? `<div class="result-explanation"><strong>解析:</strong> ${escapeHtml(q.explanation)}</div>` : ''}
            </div>
        `;
    }).join('');
}

function backToQuizList() {
    document.getElementById('quizResult').style.display = 'none';
    document.getElementById('quizArea').style.display = 'none';
    document.getElementById('quizList').style.display = 'grid';
    
    // 重新加载测验列表
    const docId = document.getElementById('quizDocSelect').value;
    if (docId) {
        loadQuizzes(docId);
    }
}

// 监听文档选择变化
document.getElementById('quizDocSelect')?.addEventListener('change', (e) => {
    const docId = e.target.value;
    if (docId) {
        loadQuizzes(docId);
    }
});
