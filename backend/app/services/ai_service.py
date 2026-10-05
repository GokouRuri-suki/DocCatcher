"""AI 服务封装 - OpenAI 兼容接口"""
import json
from typing import List, Dict, Optional, Any
from openai import OpenAI
from ..config import settings

# 单次调用能消费的最大素材量（用于如实展示"覆盖范围"与进度分母）
DEFAULT_KNOWLEDGE_CHUNKS = 20   # 知识点提取：默认参与的文本块数
QUIZ_MAX_KNOWLEDGE_POINTS = 20  # 出题：最多参考的知识点数
PLAN_MAX_KNOWLEDGE_POINTS = 30  # 学习规划：最多参考的知识点数

# 单次响应允许的最大 token（太低会把 JSON 截断，导致解析失败）
KNOWLEDGE_MAX_TOKENS = 8000
PLAN_MAX_TOKENS = 6000
QUIZ_MAX_TOKENS = 6000
ANSWER_MAX_TOKENS = 2000

# 要求模型输出的知识点条数上限（降低被截断的概率）
KNOWLEDGE_MAX_ITEMS = 40


class AIService:
    """AI 服务"""
    
    def __init__(self):
        self._client = None
        self._model = None
        self.last_finish_reason = None
    
    @property
    def client(self):
        """获取 OpenAI 客户端，如果未初始化或配置已更改，则重新初始化"""
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_api_base_url
            )
        return self._client
    
    @client.setter
    def client(self, value):
        """设置 OpenAI 客户端"""
        self._client = value
    
    @property
    def model(self):
        """获取模型名称"""
        if self._model is None:
            self._model = settings.ai_model
        return self._model
    
    @model.setter
    def model(self, value):
        """设置模型名称"""
        self._model = value
    
    def refresh_client(self):
        """强制刷新客户端配置"""
        self._client = OpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_api_base_url
        )
        self._model = settings.ai_model
    
    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """发送聊天请求"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        choice = response.choices[0]
        # 记录结束原因，便于识别"被 max_tokens 截断"的情况
        self.last_finish_reason = getattr(choice, "finish_reason", None)
        return choice.message.content

    @staticmethod
    def _salvage_list_items(text: str, key: str) -> List[Any]:
        """从被截断的 JSON 中抢救出指定数组里所有完整的对象

        模型响应因 max_tokens 被截断时，整体 JSON 无法解析，
        但已经输出的前 N 个对象往往是完整且可用的，这里把它们捞回来。
        """
        if not text:
            return []

        idx = text.find(f'"{key}"')
        if idx == -1:
            return []

        arr_start = text.find('[', idx)
        if arr_start == -1:
            return []

        items: List[Any] = []
        depth = 0
        start = None
        in_str = False
        esc = False

        for i in range(arr_start + 1, len(text)):
            ch = text[i]

            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
            elif ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        items.append(json.loads(text[start:i + 1]))
                    except Exception:
                        pass
                    start = None
            elif ch == ']' and depth == 0:
                break

        return items
    
    def extract_json(self, text: str) -> Any:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except:
            pass
        
        # 尝试提取代码块中的 JSON
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass
        
        # 尝试找到第一个 { 或 [ 到最后一个 } 或 ]
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except:
                    continue
        
        return None
    
    def extract_knowledge_points(self, text_chunks: List[Dict],
                                 max_chunks: int = DEFAULT_KNOWLEDGE_CHUNKS,
                                 max_chars: int = 40000) -> Dict:
        """从文本块中提取知识点

        max_chunks: 参与分析的文本块数量上限（默认 20，可由前端配置）
        max_chars:  拼接后的上下文字符上限，防止超出模型上下文窗口

        返回中包含 coverage 信息（实际使用了多少块 / 总共有多少块），
        以便向用户如实说明知识点的覆盖范围。
        """
        selected = text_chunks[:max(1, max_chunks)]

        combined_text = ""
        used_chunks = 0
        truncated = False
        for chunk in selected:
            piece = f"\n\n【{chunk.get('section_title', '未命名章节')}】\n{chunk['content']}"
            if combined_text and len(combined_text) + len(piece) > max_chars:
                truncated = True
                break
            combined_text += piece
            used_chunks += 1

        if truncated:
            combined_text += "\n\n（注意：内容因长度限制在此截断）"

        prompt = f"""请分析以下教材内容，提取知识点结构。

内容：
{combined_text}

请返回 JSON 格式，包含：
1. knowledge_points: 知识点列表（最多 {KNOWLEDGE_MAX_ITEMS} 条，只保留主要内容），每个知识点包含：
   - title: 标题
   - description: 简短描述
   - content: 详细内容
   - level: 层级 (1=章, 2=节, 3=知识点)
   - parent_index: 父知识点在列表中的索引（从0开始），根节点为 null
   - page_numbers: 相关页码范围

2. relations: 知识点关系列表（最多 {KNOWLEDGE_MAX_ITEMS} 条），每个关系包含：
   - source_index: 源知识点索引
   - target_index: 目标知识点索引
   - relation_type: 关系类型 (prerequisite=前置, related=相关, contains=包含)
   - description: 关系描述

请确保 JSON 格式正确、完整闭合：
{{"knowledge_points": [...], "relations": [...]}}"""

        messages = [
            {"role": "system", "content": "你是一个教育内容分析专家，擅长从教材中提取知识点结构。请只返回 JSON 格式。"},
            {"role": "user", "content": prompt}
        ]
        
        response = self.chat(messages, temperature=0.3, max_tokens=KNOWLEDGE_MAX_TOKENS)
        result = self.extract_json(response)
        salvaged = False
        
        # 被 max_tokens 截断时，整体 JSON 解析会失败；尝试抢救已输出的完整条目
        if result is None or not result.get("knowledge_points"):
            kp_items = self._salvage_list_items(response, "knowledge_points")
            rel_items = self._salvage_list_items(response, "relations")
            if kp_items:
                result = {"knowledge_points": kp_items, "relations": rel_items}
                salvaged = True
        
        if result is None:
            result = {"knowledge_points": [], "relations": [], "raw_response": response}
        
        # 附加覆盖范围信息（供如实展示，不参与业务逻辑）
        result["coverage"] = {
            "used_chunks": used_chunks,
            "requested_chunks": max_chunks,
            "total_chunks": len(text_chunks),
            "truncated": truncated,
            "salvaged": salvaged,
            "finish_reason": self.last_finish_reason,
        }
        
        return result
    
    def generate_study_plan(self, knowledge_points: List[Dict], total_days: int = 30) -> Dict:
        """生成学习规划"""
        kp_summary = []
        for i, kp in enumerate(knowledge_points[:PLAN_MAX_KNOWLEDGE_POINTS]):  # 限制数量
            kp_summary.append(f"{i+1}. [{kp.get('title', '')}] - {kp.get('description', '')[:50]}")
        
        prompt = f"""请为以下知识点制定 {total_days} 天的学习计划。

知识点列表：
{chr(10).join(kp_summary)}

请返回 JSON 格式，包含每天的学习任务：
{{
    "title": "学习计划标题",
    "description": "计划描述",
    "items": [
        {{
            "day_number": 1,
            "title": "第1天标题",
            "tasks": "具体任务描述",
            "knowledge_point_indices": [0, 1, 2]
        }}
    ]
}}

要求：
1. 合理分配每天的学习量
2. 由浅入深，循序渐进
3. 包含复习环节"""

        messages = [
            {"role": "system", "content": "你是一个学习计划规划专家。请只返回 JSON 格式。"},
            {"role": "user", "content": prompt}
        ]
        
        response = self.chat(messages, temperature=0.5, max_tokens=PLAN_MAX_TOKENS)
        result = self.extract_json(response)
        salvaged = False
        
        # 被截断时抢救已输出的完整条目
        if result is None or not result.get("items"):
            items = self._salvage_list_items(response, "items")
            if items:
                result = {"title": "学习计划", "description": "", "items": items}
                salvaged = True
        
        if result is None:
            return {"title": "学习计划", "description": "", "items": [], "raw_response": response}
        
        result["coverage"] = {"salvaged": salvaged, "finish_reason": self.last_finish_reason}
        return result
    
    def generate_quiz(self, knowledge_points: List[Dict], question_count: int = 10) -> Dict:
        """生成测验题目"""
        kp_summary = []
        for i, kp in enumerate(knowledge_points[:QUIZ_MAX_KNOWLEDGE_POINTS]):
            kp_summary.append(f"{i+1}. {kp.get('title', '')}: {kp.get('content', kp.get('description', ''))[:200]}")
        
        prompt = f"""请根据以下知识点生成 {question_count} 道测验题目。

知识点：
{chr(10).join(kp_summary)}

请返回 JSON 格式：
{{
    "title": "测验标题",
    "questions": [
        {{
            "question_type": "single_choice",  // single_choice/multiple_choice/true_false/fill_blank
            "question_text": "题目内容",
            "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}},  // 选择题必填
            "correct_answer": "A",  // 选择题为选项字母，判断题为 true/false，填空题为答案字符串
            "explanation": "解析",
            "difficulty": 3,  // 1-5
            "knowledge_point_index": 0  // 关联知识点索引
        }}
    ]
}}

要求：
1. 题型分布合理（单选、多选、判断、填空）
2. 难度梯度分布
3. 覆盖主要知识点"""

        messages = [
            {"role": "system", "content": "你是一个出题专家，擅长根据知识点生成高质量的测验题目。请只返回 JSON 格式。"},
            {"role": "user", "content": prompt}
        ]
        
        response = self.chat(messages, temperature=0.7, max_tokens=QUIZ_MAX_TOKENS)
        result = self.extract_json(response)
        salvaged = False
        
        # 同样处理被截断的情况：抢救已输出的完整题目
        if result is None or not result.get("questions"):
            items = self._salvage_list_items(response, "questions")
            if items:
                result = {"title": "测验", "questions": items}
                salvaged = True
        
        if result is None:
            return {"title": "测验", "questions": [], "raw_response": response}
        
        result["coverage"] = {"salvaged": salvaged, "finish_reason": self.last_finish_reason}
        return result
    
    def answer_question(self, question: str, relevant_chunks: List[Dict]) -> Dict:
        """基于检索到的原文片段回答问题

        始终由 AI 作答；即使没有检索到片段，也交给 AI 说明情况并给出建议，
        不再返回写死的提示文案。
        """
        if relevant_chunks:
            parts = []
            for chunk in relevant_chunks[:8]:
                page = f"第{chunk.get('page_start', '?')}-{chunk.get('page_end', '?')}页"
                section = chunk.get("section_title") or "未命名章节"
                parts.append(f"【{page}｜{section}】\n{chunk['content'][:1500]}")
            context = "\n\n".join(parts)
        else:
            context = "（本次没有检索到与问题明显相关的原文片段）"

        prompt = f"""你是一位耐心、善于讲解的学习辅导老师。请用自然、口语化的中文回答学生的问题。

教材原文片段：
{context}

学生的问题：{question}

回答要求：
1. 直接、自然地讲解，就像老师面对面说话一样，不要用生硬的模板腔或客套话
2. 结合上面的原文片段作答；引用原文内容时在句末标注来源，例如（第 42 页）
3. 如果有帮助，可以补充必要的背景知识，但要说明哪部分是原文内容、哪部分是你的补充
4. 只有当片段确实完全没有相关信息时，才说明文档里没找到相关内容，并建议学生换个更具体的问法，或指出文档中可能相关的章节
5. 篇幅适中、重点清晰；除非学生明确要求列举，否则不要机械地分 1. 2. 3.
"""

        messages = [
            {"role": "system", "content": "你是一位善于启发和讲解的学习辅导老师，回答要自然、准确、有条理。"},
            {"role": "user", "content": prompt}
        ]

        response = self.chat(messages, temperature=0.6, max_tokens=2000)

        # 来源信息直接取自检索结果（真实、可靠），不去猜模型正文里提到的页码
        seen = set()
        sources = []
        for c in relevant_chunks:
            key = (c.get("page_start"), c.get("page_end"))
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "section": c.get("section_title"),
            })

        source_pages = sorted({
            c.get("page_start") for c in relevant_chunks if c.get("page_start")
        })

        return {
            "answer": response,
            "source_pages": source_pages,
            "sources": sources,
        }


# 全局实例
ai_service = AIService()
