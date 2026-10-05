"""PDF 解析服务 - 提取文字、识别章节、文本清洗"""
import pymupdf
import re
from typing import List, Dict, Tuple
from pathlib import Path


class PDFParser:
    """PDF 解析器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = pymupdf.open(file_path)
    
    def get_total_pages(self) -> int:
        """获取总页数"""
        return len(self.doc)
    
    def extract_text_by_page(self, on_page=None) -> List[Dict]:
        """按页提取文字

        on_page: 可选回调 on_page(done, total)，用于上报真实的翻页进度
        """
        total = len(self.doc)
        pages = []
        for page_num in range(total):
            page = self.doc[page_num]
            text = page.get_text("text")
            pages.append({
                "page_number": page_num + 1,
                "text": text.strip()
            })
            if on_page is not None:
                on_page(page_num + 1, total)
        return pages
    
    def detect_sections(self, pages: List[Dict], on_page=None) -> List[Dict]:
        """识别章节结构

        on_page: 可选回调 on_page(done, total)，用于上报真实的扫描进度
        """
        sections = []
        total = len(pages)
        current_section = {
            "title": "前言",
            "level": 1,
            "start_page": 1,
            "end_page": 1,
            "content": ""
        }
        
        # 章节标题模式
        chapter_patterns = [
            r'^第[一二三四五六七八九十百千]+[章节篇部]',
            r'^第\d+[章节篇部]',
            r'^Chapter\s+\d+',
            r'^\d+\.\s+[^\d]',  # 1. 标题
            r'^\d+\.\d+\s+[^\d]',  # 1.1 标题
        ]
        
        for index, page_data in enumerate(pages):
            text = page_data["text"]
            page_num = page_data["page_number"]
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检查是否是章节标题
                is_title = False
                title_level = 0
                
                for i, pattern in enumerate(chapter_patterns):
                    if re.match(pattern, line):
                        is_title = True
                        title_level = i + 1
                        break
                
                if is_title and len(line) < 50:  # 标题通常较短
                    # 保存当前章节
                    if current_section["content"].strip():
                        sections.append(current_section)
                    
                    # 开始新章节
                    current_section = {
                        "title": line,
                        "level": title_level,
                        "start_page": page_num,
                        "end_page": page_num,
                        "content": ""
                    }
                else:
                    current_section["content"] += line + "\n"
                    current_section["end_page"] = page_num
            
            if on_page is not None:
                on_page(index + 1, total)
        
        # 添加最后一个章节
        if current_section["content"].strip():
            sections.append(current_section)
        
        return sections
    
    def clean_text(self, text: str) -> str:
        """文本清洗"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊字符（保留中文、英文、数字、标点）
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,;:!?，。；：！？、""\'\'（）()\[\]【]]', '', text)
        return text.strip()
    
    def parse(self, on_stage=None, on_progress=None) -> Dict:
        """完整解析流程

        on_stage: 可选回调 on_stage(stage_index, total_stages)
        on_progress: 可选回调 on_progress(done, total)，上报当前阶段的真实计数
        """
        def stage(index):
            if on_stage is not None:
                on_stage(index)

        # 阶段 0：解析页面（按页真实计数）
        stage(0)
        pages = self.extract_text_by_page(on_page=on_progress)

        # 阶段 1：识别章节（按页真实计数）
        stage(1)
        sections = self.detect_sections(pages, on_page=on_progress)

        # 阶段 2：文本清洗（按章节真实计数）
        stage(2)
        total_sections = len(sections)
        for i, section in enumerate(sections):
            section["content"] = self.clean_text(section["content"])
            if on_progress is not None:
                on_progress(i + 1, total_sections)

        # 先获取总页数，再关闭文档
        total_pages = len(self.doc)
        self.doc.close()
        
        return {
            "total_pages": total_pages,
            "pages": pages,
            "sections": sections
        }


def parse_pdf(file_path: str, on_stage=None, on_progress=None) -> Dict:
    """解析 PDF 文件的便捷函数"""
    parser = PDFParser(file_path)
    return parser.parse(on_stage=on_stage, on_progress=on_progress)

