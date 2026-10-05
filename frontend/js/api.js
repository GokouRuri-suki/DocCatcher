/**
 * API 封装 - 与后端通信
 */
const API_BASE = '/api';

const api = {
    // 文档相关
    async uploadDocument(file, onProgress) {
        const formData = new FormData();
        formData.append('file', file);
        
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${API_BASE}/documents/upload`);
            
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable && onProgress) {
                    onProgress((e.loaded / e.total) * 100);
                }
            };
            
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    reject(new Error(JSON.parse(xhr.responseText).detail || '上传失败'));
                }
            };
            
            xhr.onerror = () => reject(new Error('网络错误'));
            xhr.send(formData);
        });
    },

    async getDocuments() {
        const res = await fetch(`${API_BASE}/documents`);
        if (!res.ok) throw new Error('获取文档列表失败');
        return res.json();
    },

    async getDocument(id) {
        const res = await fetch(`${API_BASE}/documents/${id}`);
        if (!res.ok) throw new Error('获取文档详情失败');
        return res.json();
    },

    async deleteDocument(id) {
        const res = await fetch(`${API_BASE}/documents/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('删除失败');
        return res.json();
    },

    // 知识点相关
    async generateKnowledge(documentId, maxChunks) {
        const body = { max_chunks: maxChunks || 20 };
        const res = await fetch(`${API_BASE}/documents/${documentId}/knowledge/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.status === 409) throw new Error('该文档的知识点生成任务正在进行中，请稍候');
        if (!res.ok) throw new Error('生成知识点失败');
        return res.json();
    },

    async getKnowledgeTree(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/knowledge/tree`);
        if (!res.ok) throw new Error('获取知识树失败');
        return res.json();
    },

    async getKnowledgeGraph(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/knowledge/graph`);
        if (!res.ok) throw new Error('获取知识图谱失败');
        return res.json();
    },

    async getKnowledgePoints(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/knowledge/points`);
        if (!res.ok) throw new Error('获取知识点列表失败');
        return res.json();
    },

    async getKnowledgeProgress(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/knowledge/progress`);
        if (!res.ok) throw new Error('获取进度失败');
        return res.json();
    },

    // 统一进度查询：kind = parse | knowledge | study_plan | quiz
    async getProgress(kind, documentId) {
        const res = await fetch(`${API_BASE}/progress/${kind}/${documentId}`);
        if (!res.ok) throw new Error('获取进度失败');
        return res.json();
    },

    // 学习规划相关
    async generateStudyPlan(documentId, totalDays, startDate) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/study-plan/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ total_days: totalDays, start_date: startDate })
        });
        if (res.status === 409) throw new Error('该文档的学习规划生成任务正在进行中，请稍候');
        if (!res.ok) throw new Error('生成学习规划失败');
        return res.json();
    },

    async getStudyPlans(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/study-plan`);
        if (!res.ok) throw new Error('获取学习规划失败');
        return res.json();
    },

    async getStudyPlanDetail(planId) {
        const res = await fetch(`${API_BASE}/study-plans/${planId}`);
        if (!res.ok) throw new Error('获取规划详情失败');
        return res.json();
    },

    async updatePlanItem(itemId, completed) {
        const res = await fetch(`${API_BASE}/study-plan-items/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed })
        });
        if (!res.ok) throw new Error('更新失败');
        return res.json();
    },

    // 测验相关
    async generateQuiz(documentId, questionCount) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/quiz/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_count: questionCount })
        });
        if (res.status === 409) throw new Error('该文档的测验生成任务正在进行中，请稍候');
        if (!res.ok) throw new Error('生成测验失败');
        return res.json();
    },

    async getQuizzes(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/quizzes`);
        if (!res.ok) throw new Error('获取测验列表失败');
        return res.json();
    },

    async getQuizDetail(quizId) {
        const res = await fetch(`${API_BASE}/quizzes/${quizId}`);
        if (!res.ok) throw new Error('获取测验详情失败');
        return res.json();
    },

    async startQuiz(quizId) {
        const res = await fetch(`${API_BASE}/quizzes/${quizId}/start`, { method: 'POST' });
        if (!res.ok) throw new Error('开始测验失败');
        return res.json();
    },

    async submitQuiz(attemptId, answers) {
        const res = await fetch(`${API_BASE}/quiz-attempts/${attemptId}/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answers })
        });
        if (!res.ok) throw new Error('提交失败');
        return res.json();
    },

    async getQuizResult(attemptId) {
        const res = await fetch(`${API_BASE}/quiz-attempts/${attemptId}`);
        if (!res.ok) throw new Error('获取结果失败');
        return res.json();
    },

    // 问答相关
    async askQuestion(documentId, question) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });
        if (!res.ok) throw new Error('提问失败');
        return res.json();
    },

    // 配置相关
    async getConfig() {
        const res = await fetch(`${API_BASE}/config`);
        if (!res.ok) throw new Error('获取配置失败');
        return res.json();
    },

    async saveConfig(apiBaseUrl, apiKey, model) {
        const res = await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_base_url: apiBaseUrl,
                api_key: apiKey,
                model: model
            })
        });
        if (!res.ok) throw new Error('保存配置失败');
        return res.json();
    },

    async getConfigStatus() {
        const res = await fetch(`${API_BASE}/config/status`);
        if (!res.ok) throw new Error('获取配置状态失败');
        return res.json();
    },

    async testAIConnection() {
        const res = await fetch(`${API_BASE}/config/test`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error('测试连接失败');
        return res.json();
    }
};
