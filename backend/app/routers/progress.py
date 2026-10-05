"""统一进度查询端点

把所有长任务的进度收敛到一个接口，前端只需要一个轮询函数：
    GET /api/progress/{kind}/{document_id}

kind: parse | knowledge | study_plan | quiz

返回统一载荷，其中：
- mode == "determinate"   -> percent 为真实百分比（可计数阶段）
- mode == "indeterminate" -> percent 为 None（单次 AI 调用等不可计数阶段）
"""
from fastapi import APIRouter, HTTPException

from ..services.progress import STAGES, get_payload

router = APIRouter(prefix="/api/progress", tags=["progress"])

VALID_KINDS = set(STAGES.keys())


@router.get("/{kind}/{document_id}")
async def get_progress(kind: str, document_id: int):
    """查询某个文档某项任务的实时进度"""
    if kind not in VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"未知的任务类型 '{kind}'，可选: {', '.join(sorted(VALID_KINDS))}"
        )
    return get_payload(kind, document_id)
