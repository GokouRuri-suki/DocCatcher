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
    
    // 渲染作答区
    const optionsContainer = document.getElementById('questionOptions');

    if (question.question_type === 'fill_blank') {
        renderFillBlanks(optionsContainer, question);
        return finalizeQuestionButtons(questions);
    }

    optionsContainer.style.display = 'flex';
    optionsContainer.className = 'options';

    // 判断题：AI 常常不给 options（只有 correct_answer 的 true/false），
    // 这时界面上会一个可选项都没有。这里兜底渲染「正确 / 错误」两个固定选项。
    let entries = Object.entries(question.options || {});
    if (entries.length === 0 && question.question_type === 'true_false') {
        entries = [['true', '正确'], ['false', '错误']];
    }

    const isMultiple = question.question_type === 'multiple_choice';
    const currentAnswer = userAnswers[question.id] || (isMultiple ? [] : null);

    optionsContainer.innerHTML = entries.map(([key, value]) => {
        const isSelected = isMultiple
            ? Array.isArray(currentAnswer) && currentAnswer.includes(key)
            : String(currentAnswer) === String(key);

        return `
            <label class="option-item ${isSelected ? 'selected' : ''}">
                <input type="${isMultiple ? 'checkbox' : 'radio'}"
                       name="question-${question.id}"
                       value="${escapeHtml(key)}"
                       ${isSelected ? 'checked' : ''}
                       onchange="selectAnswer('${escapeHtml(key)}', ${isMultiple})">
                <span>${question.question_type === 'true_false' ? '' : `<strong>${escapeHtml(key)}.</strong> `}${escapeHtml(value)}</span>
            </label>
        `;
    }).join('');

    finalizeQuestionButtons(questions);
}

/**
 * 渲染填空题的输入框
 *
 * 空位数以后端返回的 blank_count 为准（后端从题干识别，只暴露「几个空」，
 * 不泄露答案）；后端没给时用同样的正则在前端兜底数一遍。
 */
function renderFillBlanks(container, question) {
    const n = Math.max(1, question.blank_count || countBlanks(question.question_text));

    const saved = userAnswers[question.id];
    const values = Array.isArray(saved) ? saved : [];

    container.style.display = 'block';
    container.className = 'fill-blanks';

    container.innerHTML = Array.from({ length: n }, (_, i) => `
        <div class="fill-blank-row">
            ${n > 1 ? `<span class="fill-blank-label">第 ${i + 1} 空</span>` : ''}
            <input type="text" class="fill-input" data-blank-index="${i}"
                   placeholder="${n > 1 ? `请输入第 ${i + 1} 空答案` : '请输入答案'}"
                   value="${escapeHtml(values[i] || '')}"
                   oninput="onFillInput()">
        </div>
    `).join('');

    container.className = 'fill-blanks';
}

/** 数题干里有几个空（与后端 BLANK_RE 保持一致） */
function countBlanks(text) {
    if (!text) return 0;
    const matches = String(text).match(/_{2,}|＿{2,}/g);
    return matches ? matches.length : 0;
}

/** 结果页：把判断题的 true/false 显示成「正确 / 错误」 */
function formatBool(value) {
    if (value === null || value === undefined || value === '') return '未作答';
    const v = String(value).trim().toLowerCase();
    if (['true', 't', '1', 'yes', 'y', '是', '对', '正确'].indexOf(v) !== -1) return '正确';
    if (['false', 'f', '0', 'no', 'n', '否', '错', '错误'].indexOf(v) !== -1) return '错误';
    return String(value);
}

/** 结果页：把填空题答案数组显示成「第1空: x ｜ 第2空: y」 */
function formatBlanks(value) {
    if (value === null || value === undefined || value === '') return '未作答';
    const parts = Array.isArray(value) ? value : [value];
    const blank = (v) => (v === '' || v === null || v === undefined) ? '未填' : v;

    if (parts.length === 1) {
        return blank(parts[0]) === '未填' ? '未作答' : String(parts[0]);
    }
    return parts.map((p, i) => `第${i + 1}空: ${blank(p)}`).join(' ｜ ');
}

/** 读取当前题的作答值（填空题读全部输入框） */
function collectCurrentAnswer(question) {
    if (!question) return null;
    if (question.question_type === 'fill_blank') {
        const inputs = document.querySelectorAll('#questionOptions .fill-input');
        if (inputs.length === 0) return userAnswers[question.id] || null;
        return Array.from(inputs).map(el => el.value);
    }
    return userAnswers[question.id] !== undefined ? userAnswers[question.id] : null;
}

/** 填空题输入时同步进 userAnswers，切题/提交都不会丢 */
function onFillInput() {
    const question = currentQuiz && currentQuiz.questions[currentQuestionIndex];
    if (!question) return;
    userAnswers[question.id] = collectCurrentAnswer(question);
}

function finalizeQuestionButtons(questions) {
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
    // 保存当前答案（填空题要把所有空都收上来）
    const question = currentQuiz.questions[currentQuestionIndex];
    const value = collectCurrentAnswer(question);
    if (value !== null) {
        userAnswers[question.id] = value;
    }
    
    currentQuestionIndex += direction;
    currentQuestionIndex = Math.max(0, Math.min(currentQuestionIndex, currentQuiz.questions.length - 1));
    renderQuestion();
}

async function handleSubmitQuiz() {
    // 保存最后一题的答案
    const question = currentQuiz.questions[currentQuestionIndex];
    const value = collectCurrentAnswer(question);
    if (value !== null) {
        userAnswers[question.id] = value;
    }
    
    if (!confirm('确定要提交答案吗？')) return;
    
    showLoading('正在提交...');
    
    try {
        // 构建答案列表：
        // 多选题提交字母数组；填空题提交各空答案的数组；其余提交字符串
        const answers = currentQuiz.questions.map(q => {
            const ans = userAnswers[q.id];
            if (q.question_type === 'fill_blank') {
                return {
                    question_id: q.id,
                    answer: Array.isArray(ans) ? ans : (ans ? [ans] : null)
                };
            }
            return {
                question_id: q.id,
                answer: ans === undefined ? null : ans
            };
        });
        
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
            answerDisplay = `你的答案: ${formatBlanks(userAnswer)} | 正确答案: ${formatBlanks(correctAnswer)}`;
        } else if (q.question_type === 'multiple_choice') {
            const userAns = Array.isArray(userAnswer) ? userAnswer.join(', ') : (userAnswer || '未作答');
            const correctAns = Array.isArray(correctAnswer) ? correctAnswer.join(', ') : correctAnswer;
            answerDisplay = `你的答案: ${userAns} | 正确答案: ${correctAns}`;
        } else if (q.question_type === 'true_false') {
            answerDisplay = `你的答案: ${formatBool(userAnswer)} | 正确答案: ${formatBool(correctAnswer)}`;
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
                <div class="md-body result-question-text">${MD.render(q.question_text)}</div>
                <p class="result-answer">${answerDisplay}</p>
                ${q.explanation ? `<div class="result-explanation"><strong>解析:</strong><div class="md-body">${MD.render(q.explanation)}</div></div>` : ''}
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
