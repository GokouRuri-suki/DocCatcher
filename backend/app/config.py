"""应用配置

重要：所有路径都基于 backend/ 目录解析为绝对路径，避免因启动时的
工作目录不同而连到不同的数据库 / 写到不同的 uploads 目录。
（历史问题：相对路径曾导致仓库根目录多出一个空的 uploads/）
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（本文件位于 backend/app/config.py）
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    # 显式用绝对路径，否则 .env 也会随工作目录漂移
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        extra="ignore",
    )

    # AI API 配置
    ai_api_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"

    # 数据库配置（默认落在 backend/study_assistant.db，与启动目录无关）
    database_url: str = f"sqlite:///{BASE_DIR / 'study_assistant.db'}"

    # 上传配置（默认落在 backend/uploads/）
    upload_dir: str = str(BASE_DIR / "uploads")
    max_upload_size_mb: int = 50

    @property
    def is_ai_configured(self) -> bool:
        """检查 AI API 是否已正确配置"""
        return bool(self.ai_api_key) and self.ai_api_key != "your-api-key-here"

    @property
    def resolved_upload_dir(self) -> Path:
        """上传目录的绝对路径（相对值按 BASE_DIR 解析）"""
        p = Path(self.upload_dir)
        return p if p.is_absolute() else (BASE_DIR / p)

    @property
    def resolved_database_url(self) -> str:
        """数据库 URL，相对的 sqlite 路径按 BASE_DIR 解析

        这样即使 .env 里写的是 sqlite:///./study_assistant.db，
        从任何工作目录启动都会连到同一个库文件。

        注意：必须用 as_posix() 拼 URL。Windows 下 Path 会给出反斜杠
        （C:\\...\\study_assistant.db），正斜杠才能保证各版本一致解析。
        """
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            # 非文件型 sqlite（含内存库 sqlite://）或其他数据库，原样使用
            return self.database_url

        raw = self.database_url[len(prefix):]
        p = Path(raw)
        if p.is_absolute():
            return f"{prefix}{p.as_posix()}"
        return f"{prefix}{(BASE_DIR / p).as_posix()}"


settings = Settings()

# 确保上传目录存在
settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
