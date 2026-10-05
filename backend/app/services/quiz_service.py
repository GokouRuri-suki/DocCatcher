"""测验服务"""
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from sqlalchemy.orm import Session
from ..models.quiz import Quiz, QuizQuestion, QuizAttempt, QuizAnswer
from ..models.knowledge import KnowledgePoint
from .ai_service import ai_service, QUIZ_MAX_KNOWLEDGE_POINTS


class QuizService:
    """测验服务"""
    
    def generate_for_document(self, db: Session, document_id: int, 
                              question_count: int = 10,
                              on_stage: Optional[Callable[[int], None]] = None,
                              on_progress: Optional[Callable[[int, int, str], None]] = None
                              ) -> Quiz:
        """为文档生成测验

        on_stage(index)                  : 阶段切换回调
        on_progress(done, total, message): 真实计数回调
        """
        # ---- 阶段 0：读取知识点（按条真实计数）----
        if on_stage:
            on_stage(0)
        knowledge_points = db.query(KnowledgePoint).filter(
            KnowledgePoint.document_id == document_id
        ).all()
        
        if not knowledge_points:
            raise ValueError("没有知识点，无法生成测验")
        
        for i in range(min(len(knowledge_points), QUIZ_MAX_KNOWLEDGE_POINTS)):
            if on_progress:
                on_progress(
                    i + 1, min(len(knowledge_points), QUIZ_MAX_KNOWLEDGE_POINTS),
                    f"已准备 {i + 1}/{min(len(knowledge_points), QUIZ_MAX_KNOWLEDGE_POINTS)} 个知识点"
                    f"（文档共 {len(knowledge_points)} 个）"
                )
        
        # 转换为字典列表
        kp_dicts = [
            {
                "title": kp.title,
                "description": kp.description,
                "content": kp.content
            }
            for kp in knowledge_points
        ]
        
        # ---- 阶段 1：AI 生成测验题目（单次调用，不可计数）----
        if on_stage:
            on_stage(1)
        result = ai_service.generate_quiz(kp_dicts, question_count)
        
        # ---- 阶段 2：写入题目（按题真实计数）----
        if on_stage:
            on_stage(2)
        
        # 创建测验
        quiz = Quiz(
            document_id=document_id,
            title=result.get("title", "测验"),
            description="",
            question_count=0
        )
        db.add(quiz)
        db.flush()
        
        # 创建题目
        questions_data = result.get("questions", [])
        total_questions = len(questions_data)
        for i, q_data in enumerate(questions_data):
            # 获取关联知识点
            kp_index = q_data.get("knowledge_point_index", 0)
            kp_id = None
            if 0 <= kp_index < len(knowledge_points):
                kp_id = knowledge_points[kp_index].id
            
            question = QuizQuestion(
                quiz_id=quiz.id,
                knowledge_point_id=kp_id,
                question_type=q_data.get("question_type", "single_choice"),
                question_text=q_data.get("question_text", ""),
                options=q_data.get("options"),
                correct_answer=q_data.get("correct_answer"),
                explanation=q_data.get("explanation", ""),
                difficulty=q_data.get("difficulty", 3),
                order=i
            )
            db.add(question)
            if on_progress and total_questions > 0:
                on_progress(i + 1, total_questions,
                            f"已写入 {i + 1}/{total_questions} 道题目")
        
        quiz.question_count = total_questions
        db.commit()
        db.refresh(quiz)
        return quiz
    
    def get_quiz_with_questions(self, db: Session, quiz_id: int) -> Optional[Dict]:
        """获取测验及其题目"""
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            return None
        
        questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz_id
        ).order_by(QuizQuestion.order).all()
        
        return {
            "id": quiz.id,
            "document_id": quiz.document_id,
            "title": quiz.title,
            "description": quiz.description,
            "question_count": quiz.question_count,
            "created_at": quiz.created_at,
            "questions": [
                {
                    "id": q.id,
                    "quiz_id": q.quiz_id,
                    "knowledge_point_id": q.knowledge_point_id,
                    "question_type": q.question_type,
                    "question_text": q.question_text,
                    "options": q.options,
                    "difficulty": q.difficulty,
                    "order": q.order
                }
                for q in questions
            ]
        }
    
    def start_attempt(self, db: Session, quiz_id: int) -> QuizAttempt:
        """开始测验尝试"""
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise ValueError("测验不存在")
        
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            total_questions=quiz.question_count
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return attempt
    
    def submit_attempt(self, db: Session, attempt_id: int, 
                       answers: List[Dict[str, Any]]) -> QuizAttempt:
        """提交测验答案"""
        attempt = db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
        if not attempt:
            raise ValueError("测验尝试不存在")
        
        correct_count = 0
        
        for answer_data in answers:
            question_id = answer_data.get("question_id")
            user_answer = answer_data.get("answer")
            
            # 获取正确答案
            question = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
            if not question:
                continue
            
            # 判断是否正确
            is_correct = self._check_answer(question.question_type, user_answer, question.correct_answer)
            if is_correct:
                correct_count += 1
            
            # 保存答案
            answer = QuizAnswer(
                attempt_id=attempt_id,
                question_id=question_id,
                user_answer=user_answer,
                is_correct=is_correct
            )
            db.add(answer)
        
        # 更新尝试记录
        attempt.correct_count = correct_count
        attempt.score = (correct_count / attempt.total_questions * 100) if attempt.total_questions > 0 else 0
        attempt.completed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(attempt)
        return attempt
    
    def _check_answer(self, question_type: str, user_answer: Any, correct_answer: Any) -> bool:
        """检查答案是否正确"""
        if user_answer is None:
            return False
        
        if question_type in ["single_choice", "true_false"]:
            return str(user_answer).strip().upper() == str(correct_answer).strip().upper()
        
        elif question_type == "multiple_choice":
            if isinstance(user_answer, list) and isinstance(correct_answer, list):
                return set(user_answer) == set(correct_answer)
            return False
        
        elif question_type == "fill_blank":
            return str(user_answer).strip().lower() == str(correct_answer).strip().lower()
        
        return False
    
    def get_attempt_result(self, db: Session, attempt_id: int) -> Optional[Dict]:
        """获取测验尝试结果"""
        attempt = db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
        if not attempt:
            return None
        
        # 获取答案
        answers = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt_id).all()
        answer_map = {a.question_id: a for a in answers}
        
        # 获取题目
        questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == attempt.quiz_id
        ).order_by(QuizQuestion.order).all()
        
        # 组合结果
        questions_with_answers = []
        for q in questions:
            answer = answer_map.get(q.id)
            questions_with_answers.append({
                "id": q.id,
                "quiz_id": q.quiz_id,
                "knowledge_point_id": q.knowledge_point_id,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "order": q.order,
                "user_answer": answer.user_answer if answer else None,
                "is_correct": answer.is_correct if answer else None
            })
        
        return {
            "attempt": {
                "id": attempt.id,
                "quiz_id": attempt.quiz_id,
                "score": attempt.score,
                "total_questions": attempt.total_questions,
                "correct_count": attempt.correct_count,
                "started_at": attempt.started_at,
                "completed_at": attempt.completed_at
            },
            "questions": questions_with_answers
        }


quiz_service = QuizService()
