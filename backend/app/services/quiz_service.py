"""测验服务"""
import re
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from sqlalchemy.orm import Session
from ..models.quiz import Quiz, QuizQuestion, QuizAttempt, QuizAnswer
from ..models.knowledge import KnowledgePoint
from .ai_service import ai_service, QUIZ_MAX_KNOWLEDGE_POINTS


# ---------------------------------------------------------------------------
# 答案规范化工具
#
# 背景：早期版本按题型存了不一致的形态 —— 多选题存字符串 'AB'、多空填空存
# 'typedef, using'，而判分函数却要求列表，导致「全选对也判错」。
#
# 现在统一为：多值一律用数组。下面这些函数既用于**写入时归一化**，
# 也用于**判分时兼容旧数据**，因此历史题目不需要迁移。
# ---------------------------------------------------------------------------

# 填空题的空位标记：2 个及以上的半角/全角下划线
BLANK_RE = re.compile(r'_{2,}|＿{2,}')

# 切分填空答案的分隔符（只在已知空位数时使用）
_ANSWER_SEPARATOR_RE = re.compile(r'[,，;；、]+')

_TRUE_TOKENS = {'true', 't', '1', 'yes', 'y', '是', '对', '正确', '√'}
_FALSE_TOKENS = {'false', 'f', '0', 'no', 'n', '否', '错', '错误', '×'}

_TRUE_HINTS = ('正确', '对', '是', 'true')
# 注意先判「假」：否则「不正确」会被 '正确' 命中
_FALSE_HINTS = ('不正确', '不对', '错误', '错', '否', 'false')


def count_blanks(text: str) -> int:
    """题干里有几个空；返回 0 表示没识别到空位标记"""
    if not text:
        return 0
    return len(BLANK_RE.findall(text))


def _norm_text(value: Any) -> str:
    """比较用的文本归一化：折叠空白 + 转小写"""
    return re.sub(r'\s+', ' ', str(value)).strip().lower()


def norm_mc_letters(value: Any) -> List[str]:
    """把多选答案归一化成去重、按字母序的【大写】列表

    兼容 'AB' / 'A,B' / ['A','B'] / ['b','a'] 等形态。
    统一大写是为了与 options 的键（'A'/'B'/'C'/'D'）一致。
    """
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        letters = set()
        for item in value:
            letters.update(norm_mc_letters(item))
        return sorted(letters)

    return sorted(set(re.findall(r'[A-Z]', str(value).upper())))


def norm_true_false(value: Any, options: Any = None) -> str:
    """把判断题答案归一化成 'true' / 'false'

    支持 bool、'true'/'false'、'正确'/'错误'、'对'/'错'、'是'/'否'、'T'/'F'、'1'/'0'。
    若给的是选项字母（如 'A'）且提供了 options，则按该选项的文本内容判真假。
    认不出来时原样返回（比较时自然不相等）。
    """
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return ''

    text = _norm_text(value)
    if not text:
        return ''

    # 选项字母 -> 用选项文本内容判断
    if len(text) == 1 and text.isalpha() and isinstance(options, dict):
        for key, label in options.items():
            if _norm_text(key) == text:
                return norm_true_false(label)

    if text in _TRUE_TOKENS:
        return 'true'
    if text in _FALSE_TOKENS:
        return 'false'

    if any(hint in text for hint in _FALSE_HINTS):
        return 'false'
    if any(hint in text for hint in _TRUE_HINTS):
        return 'true'

    return text


def split_answer_parts(value: Any, blank_count: int) -> List[str]:
    """把填空答案切成 blank_count 段

    安全护栏：**只有已知空位数时才按分隔符切分**，且
    · blank_count <= 1 时完全不切 —— 避免把「答案本身含逗号」的单空题切坏；
    · 切出的段数多于空位数时，把多余的合并回最后一段（保留原文，不丢信息）。
    """
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value]

    text = '' if value is None else str(value).strip()
    n = max(1, blank_count)

    if n <= 1:
        return [text]

    pieces = [p.strip() for p in _ANSWER_SEPARATOR_RE.split(text) if p.strip()]

    if len(pieces) == n:
        return pieces
    if len(pieces) > n:
        return pieces[:n - 1] + [', '.join(pieces[n - 1:])]
    return pieces or [text]


def normalize_correct_answer(question_type: str, question_text: str,
                             options: Any, correct_answer: Any) -> Any:
    """写入数据库前，把 AI 返回的答案归一化成规范形态

    规范：单选题存字母；多选题存字母数组；判断题存 'true'/'false'；
          填空题存字符串数组（按空顺序，单空也是单元素数组）。
    """
    if question_type == "multiple_choice":
        return norm_mc_letters(correct_answer)
    if question_type == "true_false":
        return norm_true_false(correct_answer, options)
    if question_type == "fill_blank":
        return split_answer_parts(correct_answer, count_blanks(question_text))
    return correct_answer


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

            q_type = q_data.get("question_type", "single_choice")
            q_text = q_data.get("question_text", "")
            q_options = q_data.get("options")

            question = QuizQuestion(
                quiz_id=quiz.id,
                knowledge_point_id=kp_id,
                question_type=q_type,
                question_text=q_text,
                options=q_options,
                # 归一化：多选题/填空题存数组，判断题存 'true'/'false'
                correct_answer=normalize_correct_answer(
                    q_type, q_text, q_options, q_data.get("correct_answer")
                ),
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
                    "order": q.order,
                    # 填空题的空位数：只暴露「几个空」这个结构信息，
                    # 不泄露答案内容，但让前端能渲染出正确数量的输入框
                    "blank_count": count_blanks(q.question_text)
                    if q.question_type == "fill_blank" else 0,
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
            
            # 判断是否正确（把题干/选项一并传入，供填空题看空位数、判断题解析选项字母）
            is_correct = self._check_answer(
                question.question_type,
                user_answer,
                question.correct_answer,
                blank_count=count_blanks(question.question_text),
                options=question.options,
            )
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
    
    def _check_answer(self, question_type: str, user_answer: Any, correct_answer: Any,
                      blank_count: int = 0, options: Any = None) -> bool:
        """检查答案是否正确

        对每种题型都先做「规范化」再比较，因此
        · 新写入的规范形态（数组）与
        · 历史遗留形态（多选题 'AB'、多空填空 'typedef, using'）
        都能正确判分，历史题目无需迁移。

        填空题口径：**每个空都对才算对**，无部分分。
        """
        # 未作答
        if user_answer is None:
            return False
        if isinstance(user_answer, str) and not user_answer.strip():
            return False
        if isinstance(user_answer, (list, tuple)) and len(user_answer) == 0:
            return False

        if question_type == "single_choice":
            if correct_answer is None:
                return False
            return str(user_answer).strip().upper() == str(correct_answer).strip().upper()

        if question_type == "multiple_choice":
            user_set = set(norm_mc_letters(user_answer))
            correct_set = set(norm_mc_letters(correct_answer))
            return bool(correct_set) and user_set == correct_set

        if question_type == "true_false":
            user_norm = norm_true_false(user_answer, options)
            correct_norm = norm_true_false(correct_answer, options)
            return bool(correct_norm) and user_norm == correct_norm

        if question_type == "fill_blank":
            user_parts = split_answer_parts(user_answer, blank_count)
            correct_parts = split_answer_parts(correct_answer, blank_count)
            # 空位数不一致说明错位，直接判错，避免「蒙对」
            if len(user_parts) != len(correct_parts):
                return False
            return all(
                _norm_text(u) == _norm_text(c)
                for u, c in zip(user_parts, correct_parts)
            )

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
