"""知识点 API"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from ..database import get_db
from ..models.document import Document
from ..models.knowledge import KnowledgePoint, KnowledgeRelation
from ..schemas.knowledge import (
    KnowledgePointResponse, KnowledgePointSimple, 
    KnowledgeRelationResponse, KnowledgeGraphResponse
)
from ..services.knowledge_service import knowledge_service
from ..services.progress import registry, job_key, STAGES, get_payload

router = APIRouter(prefix="/api/documents", tags=["knowledge"])

KIND = "knowledge"


class GenerateKnowledgeRequest(BaseModel):
    max_chunks: int = 20


def generate_knowledge_background(document_id: int, max_chunks: int = 20):
    """后台生成知识点（上报真实进度）"""
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
        # 节流：每 1% 或完成时上报
        if percent - state["last_percent"] >= 1.0 or done >= total:
            state["last_percent"] = percent
            registry.set_units(key, done, total, message=message)

    db = SessionLocal()
    try:
        registry.start(key, KIND, document_id, stages,
                       message=f"准备分析前 {max_chunks} 个文本块...")

        # 先删除旧的知识点
        db.query(KnowledgeRelation).filter(
            KnowledgeRelation.source_id.in_(
                db.query(KnowledgePoint.id).filter(KnowledgePoint.document_id == document_id)
            )
        ).delete(synchronize_session=False)
        db.query(KnowledgePoint).filter(KnowledgePoint.document_id == document_id).delete()
        db.commit()

        result = knowledge_service.generate_from_document(
            db, document_id,
            max_chunks=max_chunks,
            on_stage=on_stage,
            on_progress=on_progress,
        )

        points = result["points"]
        coverage = result.get("coverage") or {}

        if not points:
            registry.fail(key, "AI 未能提取出任何知识点，请检查文档内容或更换模型后重试")
            return

        used = coverage.get("used_chunks", max_chunks)
        total = coverage.get("total_chunks", used)
        msg = f"已基于 {used}/{total} 个文本块生成 {len(points)} 个知识点"
        if coverage.get("truncated"):
            msg += "（上下文已达长度上限，部分内容被截断）"
        if coverage.get("salvaged"):
            msg += "（模型响应过长被截断，已抢救出完整条目）"

        registry.complete(key, result_id=document_id, message=msg)

    except Exception as e:
        db.rollback()
        registry.fail(key, f"生成知识点失败: {e}")
    finally:
        db.close()


@router.post("/{document_id}/knowledge/generate")
async def generate_knowledge(
    document_id: int,
    background_tasks: BackgroundTasks,
    request: GenerateKnowledgeRequest = GenerateKnowledgeRequest(),
    db: Session = Depends(get_db)
):
    """生成知识点（后台任务）"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if doc.status != "processed":
        raise HTTPException(status_code=400, detail="文档尚未处理完成")

    # 并发保护：同一文档已有任务在跑时拒绝重复提交
    key = job_key(KIND, document_id)
    if registry.is_running(key):
        raise HTTPException(status_code=409, detail="该文档的知识点生成任务正在进行中，请稍候")

    max_chunks = max(1, min(request.max_chunks, 500))
    
    background_tasks.add_task(generate_knowledge_background, document_id, max_chunks)
    
    return {"message": "知识点生成任务已启动", "max_chunks": max_chunks}


@router.get("/{document_id}/knowledge/progress")
async def get_knowledge_progress(document_id: int):
    """获取知识点生成进度（统一载荷）"""
    return get_payload(KIND, document_id)


@router.get("/{document_id}/knowledge/tree")
async def get_knowledge_tree(document_id: int, db: Session = Depends(get_db)):
    """获取知识点树形结构"""
    tree = knowledge_service.get_tree(db, document_id)
    return tree


@router.get("/{document_id}/knowledge/graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(document_id: int, db: Session = Depends(get_db)):
    """获取知识图谱数据"""
    graph = knowledge_service.get_graph(db, document_id)
    return graph


@router.get("/{document_id}/knowledge/points", response_model=List[KnowledgePointSimple])
async def list_knowledge_points(document_id: int, db: Session = Depends(get_db)):
    """获取知识点列表"""
    points = db.query(KnowledgePoint).filter(
        KnowledgePoint.document_id == document_id
    ).order_by(KnowledgePoint.order).all()
    return points


@router.get("/knowledge/{point_id}")
async def get_knowledge_point(point_id: int, db: Session = Depends(get_db)):
    """获取单个知识点详情"""
    point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="知识点不存在")
    
    return {
        "id": point.id,
        "title": point.title,
        "description": point.description,
        "content": point.content,
        "level": point.level,
        "page_numbers": point.page_numbers,
        "parent_id": point.parent_id
    }
