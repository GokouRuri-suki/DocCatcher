"""统一的进度注册表

设计原则（诚实进度）：
- 可计数的阶段 -> mode="determinate"，percent 来自真实的 current/total
- 单次 AI 调用等不可计数的阶段 -> mode="indeterminate"，percent 必须为 None
- 绝不编造百分比

进程内内存实现，与现有 BackgroundTasks 架构一致（不引入 Redis/Celery）。
"""
import threading
import time
from typing import Dict, List, Optional

# 终态
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_IDLE = "idle"

TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_FAILED}

# 终态条目保留时长（秒），保证晚到的轮询仍能拿到结果
DEFAULT_TTL = 600


class ProgressRegistry:
    """线程安全的进程内进度注册表"""

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._lock = threading.Lock()
        self._jobs: Dict[str, dict] = {}
        self._ttl = ttl

    # ---------- 写入 ----------

    def start(self, key: str, kind: str, document_id: int,
              stages: List[str], message: str = "准备开始...") -> None:
        """创建一个新的任务进度"""
        now = time.time()
        with self._lock:
            self._jobs[key] = {
                "key": key,
                "kind": kind,
                "document_id": document_id,
                "status": STATUS_RUNNING,
                "stage_index": 0,
                "total_stages": len(stages),
                "stages": list(stages),
                "stage_label": stages[0] if stages else "",
                "mode": "indeterminate",
                "current": 0,
                "total": 0,
                "percent": None,
                "message": message,
                "started_at": now,
                "updated_at": now,
                "finished_at": None,
                "error": None,
                "result_id": None,
            }

    def set_stage(self, key: str, index: int, message: Optional[str] = None) -> None:
        """切换阶段。切换后默认是不确定态，直到调用 set_units 提供真实计数"""
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job["stage_index"] = index
            stages = job["stages"]
            if 0 <= index < len(stages):
                job["stage_label"] = stages[index]
            # 未提供计数前，一律按不确定处理，不编造百分比
            job["mode"] = "indeterminate"
            job["percent"] = None
            job["current"] = 0
            job["total"] = 0
            if message is not None:
                job["message"] = message
            job["updated_at"] = time.time()

    def set_units(self, key: str, current: int, total: int,
                  message: Optional[str] = None) -> None:
        """上报真实计数，切换为确定态"""
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job["mode"] = "determinate"
            job["current"] = current
            job["total"] = total
            job["percent"] = round(current / total * 100, 1) if total > 0 else None
            if message is not None:
                job["message"] = message
            job["updated_at"] = time.time()

    def set_indeterminate(self, key: str, message: Optional[str] = None) -> None:
        """显式标记为不确定态（如单次 AI 调用期间）"""
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job["mode"] = "indeterminate"
            job["percent"] = None
            job["current"] = 0
            job["total"] = 0
            if message is not None:
                job["message"] = message
            job["updated_at"] = time.time()

    def complete(self, key: str, result_id: Optional[int] = None,
                 message: str = "完成") -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            total_stages = job["total_stages"]
            job.update(
                status=STATUS_COMPLETED,
                mode="determinate",
                stage_index=max(total_stages - 1, 0),
                current=total_stages,
                total=total_stages,
                percent=100.0,
                message=message,
                result_id=result_id,
                error=None,
                updated_at=now,
                finished_at=now,
            )

    def fail(self, key: str, error: str) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job.update(
                status=STATUS_FAILED,
                mode="indeterminate",
                percent=None,
                message=str(error),
                error=str(error),
                updated_at=now,
                finished_at=now,
            )

    # ---------- 读取 ----------

    def get(self, key: str) -> Optional[dict]:
        self._purge()
        with self._lock:
            job = self._jobs.get(key)
            return dict(job) if job else None

    def is_running(self, key: str) -> bool:
        with self._lock:
            job = self._jobs.get(key)
            return bool(job and job["status"] == STATUS_RUNNING)

    def clear(self, key: str) -> None:
        with self._lock:
            self._jobs.pop(key, None)

    def _purge(self) -> None:
        """清理超过 TTL 的终态条目"""
        now = time.time()
        with self._lock:
            expired = [
                k for k, v in self._jobs.items()
                if v.get("finished_at") and now - v["finished_at"] > self._ttl
            ]
            for k in expired:
                self._jobs.pop(k, None)


# 全局实例
registry = ProgressRegistry()

# 各任务的阶段定义
STAGES = {
    "parse": ["解析 PDF 页面", "识别章节", "文本清洗", "保存分块"],
    "knowledge": ["读取文本块", "AI 提取知识点", "写入数据库"],
    "study_plan": ["读取知识点", "AI 生成学习规划", "写入学习计划"],
    "quiz": ["读取知识点", "AI 生成测验题目", "写入题目"],
}


def job_key(kind: str, document_id: int) -> str:
    """生成任务键"""
    return f"{kind}:{document_id}"


def idle_payload(kind: str, document_id: int) -> dict:
    """未开始时的载荷"""
    stages = STAGES.get(kind, [])
    return {
        "key": job_key(kind, document_id),
        "kind": kind,
        "document_id": document_id,
        "status": STATUS_IDLE,
        "stage_index": 0,
        "total_stages": len(stages),
        "stages": stages,
        "stage_label": "",
        "mode": "indeterminate",
        "current": 0,
        "total": 0,
        "percent": None,
        "message": "未开始",
        "started_at": None,
        "updated_at": None,
        "finished_at": None,
        "error": None,
        "result_id": None,
    }


def get_payload(kind: str, document_id: int) -> dict:
    """获取统一进度载荷；未开始时返回 idle"""
    job = registry.get(job_key(kind, document_id))
    return job if job is not None else idle_payload(kind, document_id)
