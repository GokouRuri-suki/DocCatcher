"""AI 学习助手 - FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .database import engine, Base
from .config import settings
from .routers import (
    documents_router,
    knowledge_router,
    study_plan_router,
    quiz_router,
    qa_router,
    config_router,
    progress_router,
)


def load_saved_ai_config() -> None:
    """把 ai_config.json 里保存的 AI 配置加载到运行时"""
    from .routers.config import load_config, CONFIG_FILE
    from .services.ai_service import ai_service

    if not CONFIG_FILE.exists():
        return

    config = load_config()
    if not config.get("api_key"):
        return

    settings.ai_api_base_url = config.get("api_base_url", "https://api.openai.com/v1")
    settings.ai_api_key = config.get("api_key", "")
    settings.ai_model = config.get("model", "gpt-4o-mini")
    ai_service.refresh_client()


def normalize_stored_paths() -> None:
    """把历史遗留的相对 file_path 归一化为绝对路径（幂等）

    早期版本用相对路径保存上传文件位置，换工作目录启动就会找不到文件。
    这里在启动时统一修正一次。
    """
    from .config import BASE_DIR
    from .database import SessionLocal
    from .models.document import Document

    db = SessionLocal()
    try:
        changed = 0
        for doc in db.query(Document).all():
            if not doc.file_path:
                continue
            p = Path(doc.file_path)
            if not p.is_absolute():
                doc.file_path = str(BASE_DIR / p)
                changed += 1
        if changed:
            db.commit()
            print(f"已将 {changed} 条文档记录的文件路径归一化为绝对路径")
    except Exception as e:
        db.rollback()
        print(f"归一化文件路径失败: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动时建表、修正历史路径、加载已保存的 AI 配置"""
    Base.metadata.create_all(bind=engine)
    normalize_stored_paths()
    load_saved_ai_config()
    yield


app = FastAPI(
    title="AI 学习助手",
    description="基于 PDF 的智能学习系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
# 警告：allow_origins=["*"] + allow_credentials=True 表示任意网页都能调用本服务。
# 本服务无认证，若绑定 0.0.0.0，同网段任何人都能消耗 AI 额度，
# 并能通过 POST /api/config 改写 base_url 把内容转发到第三方。详见 docs/STATUS.md
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(documents_router)
app.include_router(knowledge_router)
app.include_router(study_plan_router)
app.include_router(quiz_router)
app.include_router(qa_router)
app.include_router(config_router)
app.include_router(progress_router)

# 静态文件服务（前端）
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
async def root():
    """根路径 - 返回前端页面"""
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AI 学习助手 API 正在运行", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok", 
        "ai_configured": settings.is_ai_configured,
        "ai_model": settings.ai_model,
        "ai_base_url": settings.ai_api_base_url
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
