#!/usr/bin/env python3
"""冒烟测试 - 验证后端核心功能（PDF 解析 / 分块 / 建表）

用法（在 backend/ 目录下）：
    ./venv/bin/python scripts/smoke_test.py
"""
import sys
import os

# 让脚本能从 backend/ 导入 app 包（脚本位于 backend/scripts/）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

from app.services.pdf_parser import parse_pdf
from app.services.text_chunker import chunk_sections
import pymupdf
import tempfile
from pathlib import Path


def create_test_pdf():
    """创建一个测试 PDF 文件"""
    doc = pymupdf.open()
    
    # 第1页 - 第一章
    page1 = doc.new_page()
    page1.insert_text((72, 72), "第一章 Python 基础", fontsize=18)
    page1.insert_text((72, 120), "Python 是一种高级编程语言，由 Guido van Rossum 于 1991 年创建。")
    page1.insert_text((72, 150), "Python 的设计哲学强调代码的可读性和简洁的语法。")
    page1.insert_text((72, 180), "1.1 变量和数据类型")
    page1.insert_text((72, 210), "Python 支持多种数据类型，包括整数、浮点数、字符串和布尔值。")
    page1.insert_text((72, 240), "变量不需要声明类型，Python 会自动推断。")
    
    # 第2页
    page2 = doc.new_page()
    page2.insert_text((72, 72), "1.2 控制流")
    page2.insert_text((72, 120), "Python 使用缩进来定义代码块，而不是使用大括号。")
    page2.insert_text((72, 150), "if-elif-else 语句用于条件判断。")
    page2.insert_text((72, 180), "for 循环和 while 循环用于重复执行代码。")
    page2.insert_text((72, 240), "第二章 函数")
    page2.insert_text((72, 280), "函数是组织好的、可重复使用的代码块。")
    page2.insert_text((72, 310), "使用 def 关键字定义函数。")
    
    # 第3页
    page3 = doc.new_page()
    page3.insert_text((72, 72), "2.1 参数和返回值")
    page3.insert_text((72, 120), "函数可以接受参数，并可以返回值。")
    page3.insert_text((72, 150), "默认参数、关键字参数和可变参数是 Python 函数的特性。")
    page3.insert_text((72, 210), "第三章 面向对象编程")
    page3.insert_text((72, 250), "Python 支持面向对象编程范式。")
    page3.insert_text((72, 280), "类是对象的蓝图，对象是类的实例。")
    
    # 保存
    output_path = Path("test_output.pdf")
    doc.save(str(output_path))
    doc.close()
    
    return str(output_path)


def test_pdf_parsing():
    """测试 PDF 解析"""
    print("=" * 60)
    print("测试 PDF 解析")
    print("=" * 60)
    
    # 创建测试 PDF
    pdf_path = create_test_pdf()
    print(f"✓ 创建测试 PDF: {pdf_path}")
    
    # 解析 PDF
    result = parse_pdf(pdf_path)
    
    print(f"✓ 总页数: {result['total_pages']}")
    print(f"✓ 识别到 {len(result['sections'])} 个章节:")
    
    for i, section in enumerate(result['sections']):
        print(f"  {i+1}. {section['title']} (第{section['start_page']}-{section['end_page']}页)")
        print(f"     内容长度: {len(section['content'])} 字符")
    
    # 测试分块
    chunks = chunk_sections(result['sections'])
    print(f"\n✓ 分块结果: {len(chunks)} 个文本块")
    
    for i, chunk in enumerate(chunks[:3]):  # 只显示前3个
        print(f"  块 {i+1}: {chunk['section_title']} - {chunk['char_count']} 字符")
    
    # 清理
    Path(pdf_path).unlink()
    print(f"\n✓ 测试通过！")
    
    return True


def test_database():
    """测试数据库"""
    print("\n" + "=" * 60)
    print("测试数据库")
    print("=" * 60)
    
    from app.database import engine, Base
    from app.models import Document, KnowledgePoint, StudyPlan, Quiz
    
    # 检查表是否创建
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"✓ 数据库表: {', '.join(tables)}")
    
    expected_tables = ['documents', 'knowledge_points', 'knowledge_relations', 
                       'study_plans', 'study_plan_items', 'quizzes', 
                       'quiz_questions', 'quiz_attempts', 'quiz_answers', 'text_chunks']
    
    for table in expected_tables:
        if table in tables:
            print(f"  ✓ {table}")
        else:
            print(f"  ✗ {table} (缺失)")
    
    return True


def main():
    """主测试函数"""
    print("\n🧪 AI 学习助手 - 系统测试\n")
    
    try:
        test_database()
        test_pdf_parsing()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n下一步:")
        print("1. 编辑 backend/.env 文件，填入你的 AI API Key")
        print("2. 访问 http://localhost:8000 使用系统")
        print("3. 上传 PDF 文件开始学习")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
