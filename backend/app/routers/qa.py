"""问答 API - 基于 PDF 内容的智能问答

检索使用 BM25（Okapi）排序：
- 词频饱和 + 文档长度归一化，避免长块靠"字多"取胜
- IDF 权重让高频噪声词（如 C++ 书里的 "c"、"+"）权重趋近于 0，
  真正的罕见关键词（如"引用"）权重很高

这样检索出的片段才和问题真正相关，AI 才有话可说。
"""
import math
import re
import threading
from collections import Counter, OrderedDict
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models.document import Document
from ..models.chunk import TextChunk
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api", tags=["qa"])

# BM25 参数
BM25_K1 = 1.5   # 词频饱和系数
BM25_B = 0.75   # 文档长度归一化强度

# 章节标题命中的额外加权
TITLE_BOOST = 1.6

# 单字 CJK 词的降权（"的""是"这类噪声）
SINGLE_CJK_WEIGHT = 0.15

# ASCII 词提取（含 c++ / c# / stl 这类写法）
_ASCII_RE = re.compile(r'[a-z][a-z0-9+#._-]{0,29}')
# CJK 连续段
_CJK_RE = re.compile(r'[\u4e00-\u9fff]+')

# 索引缓存：LRU，最多缓存若干文档的倒排索引，防止多文档场景内存无界增长
MAX_CACHED_DOCUMENTS = 5
_INDEX_CACHE: "OrderedDict[int, Tuple[int, dict]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def tokenize(text: str) -> List[str]:
    """把文本切成检索词

    - ASCII：整词（c++、stl、pointer），不做单字拆分
    - CJK：二元组（bigram），"引用" 就是一个完整词；单字段落保留但会被降权
    """
    text = text.lower()
    tokens: List[str] = []

    for m in _ASCII_RE.finditer(text):
        tokens.append(m.group())

    for m in _CJK_RE.finditer(text):
        run = m.group()
        if len(run) == 1:
            tokens.append(run)
        else:
            for i in range(len(run) - 1):
                tokens.append(run[i:i + 2])

    return tokens


def _build_index(chunks: List[TextChunk]) -> dict:
    """为文档构建倒排索引所需统计量"""
    doc_tfs: List[Counter] = []
    doc_lengths: List[int] = []
    title_tokens: List[set] = []
    df: Counter = Counter()

    for chunk in chunks:
        tf = Counter(tokenize(chunk.content or ""))
        doc_tfs.append(tf)
        doc_lengths.append(sum(tf.values()) or 1)
        universe = set(tf)
        for t in universe:
            df[t] += 1
        title_tokens.append(set(tokenize(chunk.section_title or "")))

    total = len(chunks) or 1
    avgdl = sum(doc_lengths) / total

    return {
        "doc_tfs": doc_tfs,
        "doc_lengths": doc_lengths,
        "title_tokens": title_tokens,
        "df": df,
        "avgdl": avgdl,
        "n": total,
    }


def _get_index(db: Session, document_id: int, chunks: List[TextChunk]) -> dict:
    """取索引（LRU 缓存；块数量变化时自动失效）"""
    with _CACHE_LOCK:
        cached = _INDEX_CACHE.get(document_id)
        if cached and cached[0] == len(chunks):
            _INDEX_CACHE.move_to_end(document_id)
            return cached[1]

    # 构建索引不持锁，避免长时间阻塞其它请求
    index = _build_index(chunks)

    with _CACHE_LOCK:
        _INDEX_CACHE[document_id] = (len(chunks), index)
        _INDEX_CACHE.move_to_end(document_id)
        while len(_INDEX_CACHE) > MAX_CACHED_DOCUMENTS:
            _INDEX_CACHE.popitem(last=False)
    return index


def invalidate_index(document_id: int) -> None:
    """文档重新解析后清掉缓存"""
    with _CACHE_LOCK:
        _INDEX_CACHE.pop(document_id, None)


def _idf(index: dict, term: str) -> float:
    """BM25 的 IDF：高频词权重趋近 0，罕见词权重高"""
    n = index["n"]
    df = index["df"].get(term, 0)
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def search_relevant_chunks(db: Session, document_id: int, question: str,
                           top_k: int = 6) -> List[dict]:
    """BM25 检索最相关的文本块"""
    chunks = db.query(TextChunk).filter(
        TextChunk.document_id == document_id
    ).order_by(TextChunk.chunk_index).all()

    if not chunks:
        return []

    index = _get_index(db, document_id, chunks)
    query_terms = Counter(tokenize(question))

    if not query_terms:
        return []

    k1, b, avgdl = BM25_K1, BM25_B, index["avgdl"]

    scored: List[Tuple[float, int]] = []  # (score, chunk 下标)

    for qi, chunk in enumerate(chunks):
        tf = index["doc_tfs"][qi]
        dl = index["doc_lengths"][qi]
        length_norm = k1 * (1 - b + b * dl / avgdl)

        score = 0.0
        for term, q_weight in query_terms.items():
            f = tf.get(term)
            if not f:
                continue

            weight = _idf(index, term)

            # 查询词自身权重：单字 CJK 降权
            if len(term) == 1 and _CJK_RE.fullmatch(term):
                weight *= SINGLE_CJK_WEIGHT

            score += q_weight * weight * (f * (k1 + 1)) / (f + length_norm)

        if score <= 0:
            continue

        # 章节标题命中加权
        title_hits = sum(
            1 for term in query_terms
            if len(term) >= 2 and term in index["title_tokens"][qi]
        )
        if title_hits:
            score *= TITLE_BOOST ** min(title_hits, 3)

        scored.append((score, qi))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max(1, top_k)]

    # 按页码顺序输出，便于 AI 连贯阅读
    top.sort(key=lambda x: chunks[x[1]].chunk_index)

    return [
        {
            "content": chunks[qi].content,
            "section_title": chunks[qi].section_title,
            "page_start": chunks[qi].page_start,
            "page_end": chunks[qi].page_end,
            "chunk_index": chunks[qi].chunk_index,
            "score": round(score, 3),
        }
        for score, qi in top
    ]


class QuestionRequest(BaseModel):
    question: str
    top_k: int = 6  # 返回最相关的文本块数量


class SourceInfo(BaseModel):
    page_start: int
    page_end: int
    section: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    source_pages: List[int]
    sources: List[SourceInfo]
    matched: bool = True          # 是否检索到相关内容
    used_chunks: int = 0          # 实际喂给 AI 的片段数


@router.post("/documents/{document_id}/ask", response_model=AnswerResponse)
async def ask_question(
    document_id: int,
    request: QuestionRequest,
    db: Session = Depends(get_db)
):
    """基于 PDF 内容提问（始终由 AI 作答）"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if doc.status != "processed":
        raise HTTPException(status_code=400, detail="文档尚未处理完成")

    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    top_k = max(1, min(request.top_k, 20))
    relevant_chunks = search_relevant_chunks(db, document_id, question, top_k)

    # 注意：即使没检索到相关片段，也交给 AI 作答（由 AI 说明没找到并给出建议），
    # 不再返回写死的文案。
    result = ai_service.answer_question(question, relevant_chunks)

    return AnswerResponse(
        answer=result["answer"],
        source_pages=result["source_pages"],
        sources=[SourceInfo(**s) for s in result["sources"]],
        matched=bool(relevant_chunks),
        used_chunks=len(relevant_chunks),
    )
