"""学习规划 API"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

from ..database import get_db
from ..models.document import Document
from ..models.study_plan import StudyPlan, StudyPlanItem
from ..schemas.study_plan import (
    StudyPlanResponse, StudyPlanSimpleResponse, 
    StudyPlanItemUpdate
)
from ..services.study_plan_service import study_plan_service
from ..services.progress import registry, job_key, STAGES, get_payload

router = APIRouter(prefix="/api", tags=["study_plan"])

KIND = "study_plan"


def generate_plan_background(document_id: int, total_days: int, start_date: Optional[date]):
    """后台生成学习计划（上报真实进度）"""
    from ..database import SessionLocal

    key = job_key(KIND, document_id)
    stages = STAGES[KIND]
    state = {"last_percent": -1.0}

    def on_stage(index: int):
        state["last_percent"] = -1.0
        registry.set_stage(key, index, message=f"{stages[index]}...")

    def on_progress(done: int, total: int, message: str):
        if total <= 0:
            return
        percent = done / total * 100
        if percent - state["last_percent"] >= 1.0 or done >= total:
            state["last_percent"] = percent
            registry.set_units(key, done, total, message=message)

    db = SessionLocal()
    try:
        registry.start(key, KIND, document_id, stages, message="准备生成学习规划...")

        plan = study_plan_service.generate_for_document(
            db, document_id, total_days, start_date,
            on_stage=on_stage, on_progress=on_progress,
        )

        item_count = db.query(StudyPlanItem).filter(
            StudyPlanItem.plan_id == plan.id
        ).count()

        if item_count == 0:
            registry.fail(key, "AI 未能生成任何学习计划条目，请更换模型或稍后重试")
            return

        registry.complete(key, result_id=plan.id,
                          message=f"已生成 {item_count} 天学习计划")

    except Exception as e:
        db.rollback()
        registry.fail(key, f"生成学习规划失败: {e}")
    finally:
        db.close()


class GeneratePlanRequest(BaseModel):
    total_days: int = 30
    start_date: Optional[date] = None


@router.post("/documents/{document_id}/study-plan/generate")
async def generate_study_plan(
    document_id: int,
    request: GeneratePlanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """生成学习规划"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if doc.status != "processed":
        raise HTTPException(status_code=400, detail="文档尚未处理完成")

    key = job_key(KIND, document_id)
    if registry.is_running(key):
        raise HTTPException(status_code=409, detail="该文档的学习规划生成任务正在进行中，请稍候")
    
    background_tasks.add_task(generate_plan_background, document_id, request.total_days, request.start_date)
    
    return {"message": "学习规划生成任务已启动"}


@router.get("/documents/{document_id}/study-plan/progress")
async def get_study_plan_progress(document_id: int):
    """获取学习规划生成进度（统一载荷）"""
    return get_payload(KIND, document_id)


@router.get("/documents/{document_id}/study-plan", response_model=List[StudyPlanSimpleResponse])
async def list_study_plans(document_id: int, db: Session = Depends(get_db)):
    """获取文档的学习规划列表"""
    plans = db.query(StudyPlan).filter(
        StudyPlan.document_id == document_id
    ).order_by(StudyPlan.created_at.desc()).all()
    return plans


@router.get("/study-plans/{plan_id}")
async def get_study_plan(plan_id: int, db: Session = Depends(get_db)):
    """获取学习规划详情"""
    result = study_plan_service.get_plan_with_items(db, plan_id)
    if not result:
        raise HTTPException(status_code=404, detail="学习规划不存在")
    return result


@router.put("/study-plan-items/{item_id}")
async def update_study_plan_item(
    item_id: int,
    update: StudyPlanItemUpdate,
    db: Session = Depends(get_db)
):
    """更新学习项目完成状态"""
    item = study_plan_service.update_item_completion(db, item_id, update.completed)
    if not item:
        raise HTTPException(status_code=404, detail="学习项目不存在")
    return {"message": "更新成功", "completed": item.completed}
