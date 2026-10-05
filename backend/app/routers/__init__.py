from .documents import router as documents_router
from .knowledge import router as knowledge_router
from .study_plan import router as study_plan_router
from .quiz import router as quiz_router
from .qa import router as qa_router
from .config import router as config_router
from .progress import router as progress_router

__all__ = [
    "documents_router",
    "knowledge_router", 
    "study_plan_router",
    "quiz_router",
    "qa_router",
    "config_router",
    "progress_router",
]
