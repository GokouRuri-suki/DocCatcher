"""文档管理 API"""
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..config import settings
from ..models.document import Document
from ..models.chunk import TextChunk
from ..models.knowledge import KnowledgePoint, KnowledgeRelation
from ..models.study_plan import StudyPlan, StudyPlanItem
from ..models.quiz import Quiz, QuizQuestion, QuizAttempt, QuizAnswer
from ..schemas.document import DocumentResponse, DocumentListResponse
from ..services.pdf_parser import parse_pdf
from ..services.text_chunker import chunk_sections

router = APIRouter(prefix="/api/documents", tags=["documents"])


def process_document(document_id: int, file_path: str):
    """后台处理文档：解析 PDF、分块、保存（上报真实进度）"""
    from ..database import SessionLocal
    from ..services.progress import registry, job_key, STAGES

    key = job_key("parse", document_id)
    stages = STAGES["parse"]
    state = {"stage": 0, "last_percent": -1.0}

    def set_stage(index: int):
        """切换阶段：pdf_parser 在进入每个阶段时回调"""
        state["stage"] = index
        state["last_percent"] = -1.0
        registry.set_stage(key, index, message=f"{stages[index]}...")

    def report(done: int, total: int):
        """上报真实计数（节流：每 0.5% 或完成时上报一次）"""
        if total <= 0:
            return
        percent = done / total * 100
        if percent - state["last_percent"] >= 0.5 or done >= total:
            state["last_percent"] = percent
            registry.set_units(
                key, done, total,
                message=f"{stages[state['stage']]} {done}/{total}"
            )

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            registry.fail(key, "文档不存在")
            return

        doc.status = "parsing"
        db.commit()

        registry.start(key, "parse", document_id, stages, message="准备解析 PDF...")

        # 阶段 0-2：由 pdf_parser 按页/按章节上报真实进度
        result = parse_pdf(file_path, on_stage=set_stage, on_progress=report)
        doc.total_pages = result["total_pages"]

        # 阶段 3：保存分块，按块真实计数
        set_stage(3)
        chunks = chunk_sections(result["sections"])
        total_chunks = len(chunks)
        for i, chunk_data in enumerate(chunks):
            chunk = TextChunk(
                document_id=document_id,
                chunk_index=chunk_data["chunk_index"],
                content=chunk_data["content"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_title=chunk_data["section_title"],
                char_count=chunk_data["char_count"]
            )
            db.add(chunk)
            report(i + 1, total_chunks)

        doc.status = "processed"
        db.commit()
        registry.complete(key, result_id=document_id, message="解析完成")

    except Exception as e:
        db.rollback()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "error"
            doc.error_message = str(e)
            db.commit()
        registry.fail(key, f"解析失败: {e}")
    finally:
        db.close()


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """上传 PDF 文档"""
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")
    
    # 生成唯一文件名（上传目录用绝对路径，避免随启动目录漂移）
    ext = Path(file.filename).suffix
    filename = f"{uuid.uuid4()}{ext}"
    upload_dir = settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = str(upload_dir / filename)
    
    # 保存文件
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 获取文件大小
    file_size = Path(file_path).stat().st_size
    
    # 创建文档记录
    doc = Document(
        filename=filename,
        original_name=file.filename,
        file_path=file_path,
        status="uploading",
        file_size=file_size
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # 后台处理文档
    background_tasks.add_task(process_document, doc.id, file_path)
    
    return doc


@router.get("", response_model=List[DocumentListResponse])
async def list_documents(db: Session = Depends(get_db)):
    """获取文档列表"""
    documents = db.query(Document).order_by(Document.created_at.desc()).all()
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """获取文档详情"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """删除文档及其全部关联数据

    注意：SQLite 默认 PRAGMA foreign_keys=0，且模型未声明 ondelete，
    删除父行既不会报错也不会级联。因此必须在这里按依赖顺序显式清理，
    否则会静默留下孤儿数据（知识点/规划/测验）。
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 先取出文件路径：commit 后 ORM 对象会过期，取不到属性
    doc_file_path = doc.file_path

    try:
        # --- 知识点与关系 ---
        kp_ids = [row[0] for row in db.query(KnowledgePoint.id).filter(
            KnowledgePoint.document_id == document_id).all()]
        if kp_ids:
            db.query(KnowledgeRelation).filter(
                or_(
                    KnowledgeRelation.source_id.in_(kp_ids),
                    KnowledgeRelation.target_id.in_(kp_ids),
                )
            ).delete(synchronize_session=False)

        # --- 测验：答案 -> 题目/尝试 -> 测验 ---
        quiz_ids = [row[0] for row in db.query(Quiz.id).filter(
            Quiz.document_id == document_id).all()]
        if quiz_ids:
            question_ids = [row[0] for row in db.query(QuizQuestion.id).filter(
                QuizQuestion.quiz_id.in_(quiz_ids)).all()]
            attempt_ids = [row[0] for row in db.query(QuizAttempt.id).filter(
                QuizAttempt.quiz_id.in_(quiz_ids)).all()]

            if attempt_ids:
                db.query(QuizAnswer).filter(
                    QuizAnswer.attempt_id.in_(attempt_ids)
                ).delete(synchronize_session=False)
            if question_ids:
                db.query(QuizAnswer).filter(
                    QuizAnswer.question_id.in_(question_ids)
                ).delete(synchronize_session=False)

            db.query(QuizQuestion).filter(
                QuizQuestion.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(QuizAttempt).filter(
                QuizAttempt.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)

        # --- 学习规划：条目 -> 规划 ---
        plan_ids = [row[0] for row in db.query(StudyPlan.id).filter(
            StudyPlan.document_id == document_id).all()]
        if plan_ids:
            db.query(StudyPlanItem).filter(
                StudyPlanItem.plan_id.in_(plan_ids)).delete(synchronize_session=False)
            db.query(StudyPlan).filter(
                StudyPlan.id.in_(plan_ids)).delete(synchronize_session=False)

        # --- 知识点 / 文本块 / 文档 ---
        if kp_ids:
            db.query(KnowledgePoint).filter(
                KnowledgePoint.id.in_(kp_ids)).delete(synchronize_session=False)
        db.query(TextChunk).filter(
            TextChunk.document_id == document_id).delete(synchronize_session=False)
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 清理磁盘文件（失败不影响删除结果）
    try:
        file_path = Path(doc_file_path)
        if file_path.exists():
            file_path.unlink()
    except OSError as e:
        print(f"删除上传文件失败: {e}")

    # 清理内存中的检索索引与进度条目（避免留下脏缓存）
    try:
        from .qa import invalidate_index
        invalidate_index(document_id)
    except Exception:
        pass
    try:
        from ..services.progress import registry, job_key
        for kind in ("parse", "knowledge", "study_plan", "quiz"):
            registry.clear(job_key(kind, document_id))
    except Exception:
        pass

    return {"message": "删除成功"}
