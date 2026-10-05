"""学习规划服务"""
from typing import List, Dict, Optional, Callable
from datetime import date
from sqlalchemy.orm import Session
from ..models.study_plan import StudyPlan, StudyPlanItem
from ..models.knowledge import KnowledgePoint
from .ai_service import ai_service, PLAN_MAX_KNOWLEDGE_POINTS


class StudyPlanService:
    """学习规划服务"""
    
    def generate_for_document(self, db: Session, document_id: int, total_days: int = 30, 
                              start_date: Optional[date] = None,
                              on_stage: Optional[Callable[[int], None]] = None,
                              on_progress: Optional[Callable[[int, int, str], None]] = None
                              ) -> StudyPlan:
        """为文档生成学习规划

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
            raise ValueError("没有知识点，无法生成学习计划")
        
        for i in range(min(len(knowledge_points), PLAN_MAX_KNOWLEDGE_POINTS)):
            if on_progress:
                on_progress(
                    i + 1, min(len(knowledge_points), PLAN_MAX_KNOWLEDGE_POINTS),
                    f"已准备 {i + 1}/{min(len(knowledge_points), PLAN_MAX_KNOWLEDGE_POINTS)} 个知识点"
                    f"（文档共 {len(knowledge_points)} 个）"
                )
        
        # 转换为字典列表
        kp_dicts = [
            {
                "title": kp.title,
                "description": kp.description,
                "content": kp.content,
                "level": kp.level
            }
            for kp in knowledge_points
        ]
        
        # ---- 阶段 1：AI 生成学习规划（单次调用，不可计数）----
        if on_stage:
            on_stage(1)
        result = ai_service.generate_study_plan(kp_dicts, total_days)
        
        # ---- 阶段 2：写入学习计划（按条目真实计数）----
        if on_stage:
            on_stage(2)
        
        # 创建学习计划
        plan = StudyPlan(
            document_id=document_id,
            title=result.get("title", "学习计划"),
            description=result.get("description", ""),
            total_days=total_days,
            start_date=start_date or date.today()
        )
        db.add(plan)
        db.flush()
        
        # 创建学习项目
        items_data = result.get("items", [])
        total_items = len(items_data)
        for i, item_data in enumerate(items_data):
            # 将知识点索引转换为 ID
            kp_indices = item_data.get("knowledge_point_indices", [])
            kp_ids = []
            for idx in kp_indices:
                if 0 <= idx < len(knowledge_points):
                    kp_ids.append(knowledge_points[idx].id)
            
            item = StudyPlanItem(
                plan_id=plan.id,
                day_number=item_data.get("day_number", 1),
                title=item_data.get("title", f"第{item_data.get('day_number', 1)}天"),
                tasks=item_data.get("tasks", ""),
                knowledge_point_ids=kp_ids,
                completed=False,
                order=item_data.get("day_number", 1)
            )
            db.add(item)
            if on_progress and total_items > 0:
                on_progress(i + 1, total_items,
                            f"已写入 {i + 1}/{total_items} 天计划")
        
        db.commit()
        db.refresh(plan)
        return plan
    
    def get_plan_with_items(self, db: Session, plan_id: int) -> Optional[Dict]:
        """获取学习计划及其项目"""
        plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
        if not plan:
            return None
        
        items = db.query(StudyPlanItem).filter(
            StudyPlanItem.plan_id == plan_id
        ).order_by(StudyPlanItem.order).all()
        
        return {
            "id": plan.id,
            "document_id": plan.document_id,
            "title": plan.title,
            "description": plan.description,
            "total_days": plan.total_days,
            "start_date": plan.start_date,
            "created_at": plan.created_at,
            "items": [
                {
                    "id": item.id,
                    "plan_id": item.plan_id,
                    "day_number": item.day_number,
                    "title": item.title,
                    "tasks": item.tasks,
                    "knowledge_point_ids": item.knowledge_point_ids,
                    "completed": item.completed,
                    "order": item.order
                }
                for item in items
            ]
        }
    
    def update_item_completion(self, db: Session, item_id: int, completed: bool) -> Optional[StudyPlanItem]:
        """更新学习项目完成状态"""
        item = db.query(StudyPlanItem).filter(StudyPlanItem.id == item_id).first()
        if not item:
            return None
        
        item.completed = completed
        db.commit()
        db.refresh(item)
        return item


study_plan_service = StudyPlanService()
