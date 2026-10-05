"""知识点服务 - 生成和管理知识点"""
from typing import List, Dict, Optional, Callable
from sqlalchemy.orm import Session
from ..models.knowledge import KnowledgePoint, KnowledgeRelation
from ..models.chunk import TextChunk
from .ai_service import ai_service


class KnowledgeService:
    """知识点服务"""
    
    def generate_from_document(
        self,
        db: Session,
        document_id: int,
        max_chunks: int = 20,
        on_stage: Optional[Callable[[int], None]] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """从文档生成知识点

        on_stage(index)                 : 阶段切换回调
        on_progress(done, total, message): 真实计数回调
        返回 {"points": [...], "coverage": {...}}
        """
        # ---- 阶段 0：读取文本块（按块真实计数）----
        if on_stage:
            on_stage(0)
        chunks = db.query(TextChunk).filter(TextChunk.document_id == document_id).all()
        total_chunks = len(chunks)
        if not chunks:
            raise ValueError("没有文本块，请先完成文档解析")

        # 只按"真正送去分析"的块数上报，不虚增分母
        used_chunks = min(total_chunks, max(1, max_chunks))
        for i in range(used_chunks):
            if on_progress:
                on_progress(
                    i + 1, used_chunks,
                    f"已准备 {i + 1}/{used_chunks} 个文本块用于分析（文档共 {total_chunks} 个）"
                )

        # 转换为字典列表
        chunk_dicts = [
            {
                "content": c.content,
                "section_title": c.section_title,
                "page_start": c.page_start,
                "page_end": c.page_end
            }
            for c in chunks
        ]
        
        # ---- 阶段 1：AI 提取知识点（单次调用，不可计数）----
        if on_stage:
            on_stage(1)
        result = ai_service.extract_knowledge_points(chunk_dicts, max_chunks=max_chunks)
        
        knowledge_points_data = result.get("knowledge_points", [])
        relations_data = result.get("relations", [])
        coverage = result.get("coverage", {})
        
        # ---- 阶段 2：写入数据库（按行真实计数）----
        if on_stage:
            on_stage(2)
        
        total_rows = len(knowledge_points_data) + len(relations_data)
        done = 0
        
        # 创建知识点
        created_points = []
        for i, kp_data in enumerate(knowledge_points_data):
            kp = KnowledgePoint(
                document_id=document_id,
                title=kp_data.get("title", f"知识点{i+1}"),
                description=kp_data.get("description", ""),
                content=kp_data.get("content", ""),
                level=kp_data.get("level", 1),
                order=i,
                page_numbers=kp_data.get("page_numbers", ""),
                parent_id=None  # 稍后设置
            )
            db.add(kp)
            db.flush()  # 获取 ID
            created_points.append(kp)
            done += 1
            if on_progress and total_rows > 0:
                on_progress(done, total_rows, f"已写入 {done}/{total_rows} 条记录")
        
        # 设置父子关系
        for i, kp_data in enumerate(knowledge_points_data):
            parent_index = kp_data.get("parent_index")
            if parent_index is not None and 0 <= parent_index < len(created_points):
                created_points[i].parent_id = created_points[parent_index].id
        
        # 创建关系
        for rel_data in relations_data:
            source_idx = rel_data.get("source_index")
            target_idx = rel_data.get("target_index")
            
            if (source_idx is not None and target_idx is not None and
                0 <= source_idx < len(created_points) and
                0 <= target_idx < len(created_points)):
                
                relation = KnowledgeRelation(
                    source_id=created_points[source_idx].id,
                    target_id=created_points[target_idx].id,
                    relation_type=rel_data.get("relation_type", "related"),
                    description=rel_data.get("description", "")
                )
                db.add(relation)
            
            done += 1
            if on_progress and total_rows > 0:
                on_progress(done, total_rows, f"已写入 {done}/{total_rows} 条记录")
        
        db.commit()
        return {"points": created_points, "coverage": coverage}
    
    def get_tree(self, db: Session, document_id: int) -> List[Dict]:
        """获取知识点树形结构"""
        # 获取所有知识点
        points = db.query(KnowledgePoint).filter(
            KnowledgePoint.document_id == document_id
        ).order_by(KnowledgePoint.order).all()
        
        # 构建树
        point_map = {p.id: {"id": p.id, "title": p.title, "description": p.description, 
                           "level": p.level, "parent_id": p.parent_id, "page_numbers": p.page_numbers,
                           "children": []} for p in points}
        
        roots = []
        for p in points:
            node = point_map[p.id]
            if p.parent_id is None:
                roots.append(node)
            elif p.parent_id in point_map:
                point_map[p.parent_id]["children"].append(node)
        
        return roots
    
    def get_graph(self, db: Session, document_id: int) -> Dict:
        """获取知识图谱数据"""
        # 获取知识点
        points = db.query(KnowledgePoint).filter(
            KnowledgePoint.document_id == document_id
        ).all()
        
        # 获取关系
        point_ids = [p.id for p in points]
        relations = db.query(KnowledgeRelation).filter(
            (KnowledgeRelation.source_id.in_(point_ids)) |
            (KnowledgeRelation.target_id.in_(point_ids))
        ).all()
        
        nodes = [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "level": p.level,
                "parent_id": p.parent_id,
                "page_numbers": p.page_numbers
            }
            for p in points
        ]
        
        edges = [
            {
                "id": r.id,
                "source_id": r.source_id,
                "target_id": r.target_id,
                "relation_type": r.relation_type,
                "description": r.description
            }
            for r in relations
        ]
        
        return {"nodes": nodes, "edges": edges}


knowledge_service = KnowledgeService()
