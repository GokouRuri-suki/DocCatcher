#!/usr/bin/env python3
"""冒烟测试 - 验证后端核心功能（PDF 解析 / 分块 / 建表）

用法（在任意目录均可）：
    backend/venv/bin/python backend/scripts/smoke_test.py     # Linux/macOS
    backend\\venv\\Scripts\\python.exe backend\\scripts\\smoke_test.py   # Windows

不使用任何非 ASCII 符号（例如对勾、叉号、烧瓶等 emoji），否则在 Windows 的
GBK 控制台下会抛 UnicodeEncodeError。仅用 [OK] / [FAIL] / [WARN] 标记。
"""
import sys
import os

# Windows 控制台尽量切到 UTF-8，避免中文输出乱码；失败不影响运行
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    
    # 保存到系统临时目录，不污染当前工作目录
    output_path = Path(tempfile.gettempdir()) / "ai_study_assistant_smoke_test.pdf"
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
    print(f"[OK] 创建测试 PDF: {pdf_path}")
    
    # 解析 PDF
    result = parse_pdf(pdf_path)
    
    print(f"[OK] 总页数: {result['total_pages']}")
    print(f"[OK] 识别到 {len(result['sections'])} 个章节:")
    
    for i, section in enumerate(result['sections']):
        print(f"  {i+1}. {section['title']} (第{section['start_page']}-{section['end_page']}页)")
        print(f"     内容长度: {len(section['content'])} 字符")
    
    # 测试分块
    chunks = chunk_sections(result['sections'])
    print(f"\n[OK] 分块结果: {len(chunks)} 个文本块")
    
    for i, chunk in enumerate(chunks[:3]):  # 只显示前3个
        print(f"  块 {i+1}: {chunk['section_title']} - {chunk['char_count']} 字符")
    
    # 清理
    Path(pdf_path).unlink()
    print(f"\n[OK] 测试通过！")
    
    return True


def test_database():
    """测试数据库建表

    注意：建表动作原本挂在 app/main.py 的模块级，后来随 lifespan 迁移挪进了
    生命周期钩子 —— 也就是说"光是 import app"已经不会建表了。因此这里必须
    自己显式建表，否则自检会在应用启动前跑，看到的是空库。
    """
    print("\n" + "=" * 60)
    print("测试数据库")
    print("=" * 60)
    
    from app.database import engine, Base
    from app.models import Document, KnowledgePoint, StudyPlan, Quiz
    
    # 显式建表（幂等），与应用启动时做的事一致
    Base.metadata.create_all(bind=engine)
    
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    
    expected_tables = ['documents', 'knowledge_points', 'knowledge_relations', 
                       'study_plans', 'study_plan_items', 'quizzes', 
                       'quiz_questions', 'quiz_attempts', 'quiz_answers', 'text_chunks']
    
    missing = [t for t in expected_tables if t not in tables]
    
    print(f"[OK] 数据库表共 {len(tables)} 张: {', '.join(sorted(tables))}")
    for table in expected_tables:
        if table in tables:
            print(f"  [OK]   {table}")
        else:
            print(f"  [FAIL] {table} (缺失)")
    
    if missing:
        print(f"\n[FAIL] 缺少 {len(missing)} 张表: {', '.join(missing)}")
        return False
    
    return True


def main():
    """主测试函数"""
    print("\n=== AI 学习助手 - 环境自检 ===\n")

    failures = []

    try:
        # 每项都检查返回值：任一失败都必须让退出码非 0，
        # 否则启动脚本会把"自检通过"这个结论建立在假象上
        if not test_database():
            failures.append("数据库建表")
        if not test_pdf_parsing():
            failures.append("PDF 解析")
    except Exception as e:
        print(f"\n[FAIL] 自检异常: {e}")
        import traceback
        traceback.print_exc()
        failures.append(f"异常: {e}")

    print("\n" + "=" * 60)
    if failures:
        print(f"[FAIL] 自检未通过（{len(failures)} 项）: {', '.join(failures)}")
        print("=" * 60)
        return 1

    print("[OK] 所有检查通过")
    print("=" * 60)
    print("\n下一步（由启动脚本自动完成，也可手动执行）:")
    print("1. 启动服务:  ./start.sh      (Windows: 双击 start.bat)")
    print("2. 打开浏览器 http://localhost:8000")
    print("3. 左下角 [AI 设置] 填入你的 API 地址与 Key 后即可使用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
