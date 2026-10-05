"""文本分块服务 - 将长文本分割成适合 AI 处理的块"""
from typing import List, Dict


class TextChunker:
    """文本分块器"""
    
    def __init__(self, chunk_size: int = 1500, overlap: int = 200):
        self.chunk_size = chunk_size  # 每块目标字符数
        self.overlap = overlap  # 块之间重叠字符数
    
    def chunk_by_section(self, sections: List[Dict]) -> List[Dict]:
        """按章节分块，保持章节信息"""
        chunks = []
        chunk_index = 0
        
        for section in sections:
            content = section["content"]
            if not content.strip():
                continue
            
            # 如果章节内容较短，整块保存
            if len(content) <= self.chunk_size:
                chunks.append({
                    "chunk_index": chunk_index,
                    "content": content,
                    "section_title": section["title"],
                    "page_start": section["start_page"],
                    "page_end": section["end_page"],
                    "char_count": len(content)
                })
                chunk_index += 1
            else:
                # 长章节需要进一步分割
                sub_chunks = self._split_long_text(content)
                for sub_content in sub_chunks:
                    chunks.append({
                        "chunk_index": chunk_index,
                        "content": sub_content,
                        "section_title": section["title"],
                        "page_start": section["start_page"],
                        "page_end": section["end_page"],
                        "char_count": len(sub_content)
                    })
                    chunk_index += 1
        
        return chunks
    
    def _split_long_text(self, text: str) -> List[str]:
        """分割长文本"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # 如果还有剩余文本，尝试在句子边界处分割
            if end < len(text):
                # 查找最近的句子结束符
                sentence_endings = ['。', '！', '？', '.', '!', '?', '\n']
                last_ending = -1
                
                for ending in sentence_endings:
                    pos = text.rfind(ending, start + self.chunk_size // 2, end)
                    if pos > last_ending:
                        last_ending = pos
                
                if last_ending > start:
                    end = last_ending + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # 移动起点，保留重叠
            start = end - self.overlap if end < len(text) else end
        
        return chunks
    
    def chunk_text(self, text: str, page_start: int = 1, page_end: int = 1) -> List[Dict]:
        """直接对文本进行分块"""
        sub_chunks = self._split_long_text(text)
        chunks = []
        
        for i, content in enumerate(sub_chunks):
            chunks.append({
                "chunk_index": i,
                "content": content,
                "section_title": None,
                "page_start": page_start,
                "page_end": page_end,
                "char_count": len(content)
            })
        
        return chunks


def chunk_sections(sections: List[Dict], chunk_size: int = 1500, overlap: int = 200) -> List[Dict]:
    """对章节列表进行分块的便捷函数"""
    chunker = TextChunker(chunk_size, overlap)
    return chunker.chunk_by_section(sections)
