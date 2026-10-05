"""测验 API"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from ..database import get_db
from ..models.document import Document
from ..models.quiz import Quiz
from ..schemas.quiz import (
    QuizResponse, QuizDetailResponse, QuizSubmitRequest,
    QuizResultResponse
)
from ..services.quiz_service import quiz_service
from ..services.progress import registry, job_key, STAGES, get_payload

router = APIRouter(prefix="/api", tags=["quiz"])

KIND = "quiz"


def generate_quiz_background(document_id: int, question_count: int):
    """后台生成测验（上报真实进度）"""
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
        registry.start(key, KIND, document_id, stages,
                       message=f"准备生成 {question_count} 道题目...")

        quiz = quiz_service.generate_for_document(
            db, document_id, question_count,
            on_stage=on_stage, on_progress=on_progress,
        )

        if not quiz.question_count:
            registry.fail(key, "AI 未能生成任何题目，请更换模型或稍后重试")
            return

        registry.complete(key, result_id=quiz.id,
                          message=f"已生成 {quiz.question_count} 道题目")

    except Exception as e:
        db.rollback()
        registry.fail(key, f"生成测验失败: {e}")
    finally:
        db.close()


class GenerateQuizRequest(BaseModel):
    question_count: int = 10


@router.post("/documents/{document_id}/quiz/generate")
async def generate_quiz(
    document_id: int,
    request: GenerateQuizRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """生成测验"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if doc.status != "processed":
        raise HTTPException(status_code=400, detail="文档尚未处理完成")

    key = job_key(KIND, document_id)
    if registry.is_running(key):
        raise HTTPException(status_code=409, detail="该文档的测验生成任务正在进行中，请稍候")
    
    background_tasks.add_task(generate_quiz_background, document_id, request.question_count)
    
    return {"message": "测验生成任务已启动"}


@router.get("/documents/{document_id}/quiz/progress")
async def get_quiz_progress(document_id: int):
    """获取测验生成进度（统一载荷）"""
    return get_payload(KIND, document_id)


@router.get("/documents/{document_id}/quizzes", response_model=List[QuizResponse])
async def list_quizzes(document_id: int, db: Session = Depends(get_db)):
    """获取文档的测验列表"""
    quizzes = db.query(Quiz).filter(
        Quiz.document_id == document_id
    ).order_by(Quiz.created_at.desc()).all()
    return quizzes


@router.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    """获取测验详情（含题目）"""
    result = quiz_service.get_quiz_with_questions(db, quiz_id)
    if not result:
        raise HTTPException(status_code=404, detail="测验不存在")
    return result


@router.post("/quizzes/{quiz_id}/start")
async def start_quiz(quiz_id: int, db: Session = Depends(get_db)):
    """开始测验"""
    try:
        attempt = quiz_service.start_attempt(db, quiz_id)
        return {"attempt_id": attempt.id, "message": "测验已开始"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/quiz-attempts/{attempt_id}/submit")
async def submit_quiz(
    attempt_id: int,
    request: QuizSubmitRequest,
    db: Session = Depends(get_db)
):
    """提交测验答案"""
    try:
        answers = [{"question_id": a.question_id, "answer": a.answer} for a in request.answers]
        attempt = quiz_service.submit_attempt(db, attempt_id, answers)
        return {
            "attempt_id": attempt.id,
            "score": attempt.score,
            "correct_count": attempt.correct_count,
            "total_questions": attempt.total_questions,
            "message": "提交成功"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/quiz-attempts/{attempt_id}")
async def get_quiz_result(attempt_id: int, db: Session = Depends(get_db)):
    """获取测验结果"""
    result = quiz_service.get_attempt_result(db, attempt_id)
    if not result:
        raise HTTPException(status_code=404, detail="测验记录不存在")
    return result
