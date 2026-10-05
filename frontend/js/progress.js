/**
 * 统一进度条组件
 *
 * 核心原则：绝不编造百分比。
 * - payload.mode === 'determinate'   -> 显示真实的 current/total 百分比
 * - payload.mode === 'indeterminate' -> 显示滑动动画 + 阶段标签 + 已用时长，
 *                                       不显示任何百分比数字
 *
 * 用法：
 *   ProgressBar.show('myContainer', 'knowledge');
 *   ProgressBar.startPolling('knowledge', docId, {
 *       containerId: 'myContainer',
 *       onComplete: (payload) => {...},
 *       onFail: (payload) => {...}
 *   });
 *   ProgressBar.stopPolling('knowledge', docId);
 */
const ProgressBar = (function () {
    // kind -> 显示标题
    const TITLES = {
        parse: '解析 PDF',
        knowledge: '生成知识点',
        study_plan: '生成学习规划',
        quiz: '生成测验'
    };

    const pollers = {};   // taskKey -> intervalId
    const tickers = {};   // taskKey -> intervalId (已用时长)
    const states = {};    // taskKey -> { startedAt }
    const active = {};    // taskKey -> { kind, docId, options, startedAt } 供暂停后恢复

    function taskKey(kind, docId) {
        return kind + ':' + docId;
    }

    function el(container, cls) {
        return container.querySelector('.' + cls);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    /** 创建（或复用）进度条 DOM */
    function ensure(containerId, kind) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        let box = container.querySelector('.task-progress');
        if (!box) {
            box = document.createElement('div');
            box.className = 'task-progress';
            box.innerHTML = [
                '<div class="task-progress-head">',
                '  <span class="task-progress-title"></span>',
                '  <span class="task-progress-stage"></span>',
                '</div>',
                '<div class="progress-bar">',
                '  <div class="progress-bar-fill"></div>',
                '</div>',
                '<div class="task-progress-foot">',
                '  <span class="task-progress-message"></span>',
                '  <span class="task-progress-meta"></span>',
                '</div>'
            ].join('');
            container.prepend(box);
        }

        box.style.display = 'block';
        el(box, 'task-progress-title').textContent = TITLES[kind] || '处理中';
        return box;
    }

    function show(containerId, kind) {
        return ensure(containerId, kind);
    }

    /** 按载荷渲染 */
    function render(containerId, kind, payload) {
        const box = ensure(containerId, kind);
        if (!box) return;

        const totalStages = payload.total_stages || 0;
        const stageIndex = payload.stage_index || 0;

        // 阶段标签：2/3 · AI 提取知识点
        let stageText = payload.stage_label || '';
        if (totalStages > 0 && payload.status === 'running') {
            stageText = `阶段 ${Math.min(stageIndex + 1, totalStages)}/${totalStages} · ${stageText}`;
        } else if (payload.status === 'completed') {
            stageText = '已完成';
        } else if (payload.status === 'failed') {
            stageText = '失败';
        }
        el(box, 'task-progress-stage').textContent = stageText;
        el(box, 'task-progress-message').textContent = payload.message || '';

        const fill = el(box, 'progress-bar-fill');
        const meta = el(box, 'task-progress-meta');

        if (payload.mode === 'determinate' && typeof payload.percent === 'number') {
            // 真实百分比
            fill.classList.remove('indeterminate');
            fill.style.width = Math.max(0, Math.min(100, payload.percent)) + '%';
            const counts = (payload.total > 0)
                ? ` ${payload.current}/${payload.total}`
                : '';
            meta.textContent = `${payload.percent}%${counts}`;
        } else {
            // 不确定态：动画 + 真实已用时长，不显示百分比
            fill.classList.add('indeterminate');
            fill.style.width = '100%';
            meta.textContent = elapsedText(payload);
        }

        box.classList.toggle('is-failed', payload.status === 'failed');
        box.classList.toggle('is-completed', payload.status === 'completed');
    }

    /** 已用时长（真实计时，来自 started_at） */
    function elapsedText(payload) {
        let startedAt = null;

        if (payload && payload.started_at) {
            startedAt = payload.started_at;
        } else if (payload && payload.key && states[payload.key]) {
            startedAt = states[payload.key].startedAt;
        }

        if (!startedAt) return '';

        const secs = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
        if (secs < 60) return `${secs}s`;
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        return `${m}m ${s}s`;
    }

    function hide(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const box = container.querySelector('.task-progress');
        if (box) box.style.display = 'none';
    }

    /** 每秒刷新已用时长（仅不确定态需要） */
    function startTicker(containerId, kind, taskKeyStr) {
        stopTicker(taskKeyStr);
        tickers[taskKeyStr] = setInterval(function () {
            const container = document.getElementById(containerId);
            if (!container) return;
            const box = container.querySelector('.task-progress');
            if (!box) return;
            const fill = el(box, 'progress-bar-fill');
            if (!fill || !fill.classList.contains('indeterminate')) return;
            const meta = el(box, 'task-progress-meta');
            if (meta) meta.textContent = elapsedText(null);
        }, 1000);
    }

    function stopTicker(taskKeyStr) {
        if (tickers[taskKeyStr]) {
            clearInterval(tickers[taskKeyStr]);
            delete tickers[taskKeyStr];
        }
    }

    /**
     * 轮询进度
     * onComplete(payload) / onFail(payload) 只会被调用一次
     */
    function startPolling(kind, docId, options) {
        const opts = options || {};
        const containerId = opts.containerId || ('tab-' + kind);
        const interval = opts.interval || 1000;
        const key = taskKey(kind, docId);

        // 记录活动任务，供页面重新可见时恢复
        const previous = active[key];
        const startedAt = opts.startedAt
            || (previous && previous.startedAt)
            || (Date.now() / 1000);
        active[key] = {
            kind: kind,
            docId: docId,
            options: Object.assign({}, opts, { startedAt: startedAt }),
            startedAt: startedAt
        };

        clearTimers(key);

        states[key] = { startedAt: startedAt };
        show(containerId, kind);
        startTicker(containerId, kind, key);

        let done = false;

        async function tick() {
            if (done) return;
            try {
                const payload = await api.getProgress(kind, docId);
                render(containerId, kind, payload);

                if (payload.status === 'completed') {
                    done = true;
                    finish(key);
                    if (opts.onComplete) opts.onComplete(payload);
                } else if (payload.status === 'failed') {
                    done = true;
                    finish(key);
                    if (opts.onFail) opts.onFail(payload);
                }
            } catch (err) {
                console.error('获取进度失败:', err);
            }
        }

        pollers[key] = setInterval(tick, interval);
        tick();   // 立即拉一次，不必空等一个轮询周期
    }

    /** 只清理定时器，保留活动任务记录 */
    function clearTimers(key) {
        if (pollers[key]) {
            clearInterval(pollers[key]);
            delete pollers[key];
        }
        stopTicker(key);
    }

    /** 任务终止：连活动记录一起清掉 */
    function finish(key) {
        clearTimers(key);
        delete states[key];
        delete active[key];
    }

    /** 显式停止某个任务（用户主动放弃） */
    function stopPolling(kind, docId) {
        finish(taskKey(kind, docId));
    }

    /** 暂停所有轮询（页面不可见时） */
    function pauseAll() {
        Object.keys(pollers).forEach(function (k) {
            clearInterval(pollers[k]);
            delete pollers[k];
        });
        Object.keys(tickers).forEach(function (k) {
            clearInterval(tickers[k]);
            delete tickers[k];
        });
    }

    /** 恢复所有仍在进行中的任务 */
    function resumeAll() {
        Object.keys(active).forEach(function (k) {
            const task = active[k];
            if (!task) return;
            startPolling(task.kind, task.docId, task.options);
        });
    }

    /** 彻底清理（页面卸载） */
    function stopAll() {
        pauseAll();
        Object.keys(active).forEach(function (k) { delete active[k]; });
        Object.keys(states).forEach(function (k) { delete states[k]; });
    }

    window.addEventListener('beforeunload', stopAll);

    // 页面切走时暂停轮询，切回来时自动恢复（否则进度条会永久停住）
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            pauseAll();
        } else {
            resumeAll();
        }
    });

    return {
        show: show,
        render: render,
        hide: hide,
        startPolling: startPolling,
        stopPolling: stopPolling,
        pauseAll: pauseAll,
        resumeAll: resumeAll,
        stopAll: stopAll
    };
})();
