"""配置管理 API"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from cryptography.fernet import Fernet
import base64
import os

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_FILE = Path(__file__).parent.parent.parent / "ai_config.json"
KEY_FILE = Path(__file__).parent.parent.parent / ".encryption_key"


def get_encryption_key() -> bytes:
    """获取或生成加密密钥"""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    else:
        # 生成新的密钥
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        return key


def encrypt_api_key(api_key: str) -> str:
    """加密 API Key"""
    if not api_key:
        return ""
    f = Fernet(get_encryption_key())
    encrypted = f.encrypt(api_key.encode())
    return encrypted.decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """解密 API Key"""
    if not encrypted_key:
        return ""
    try:
        f = Fernet(get_encryption_key())
        decrypted = f.decrypt(encrypted_key.encode())
        return decrypted.decode()
    except Exception:
        return ""


class ConfigRequest(BaseModel):
    api_base_url: str
    api_key: str
    model: str


class ConfigResponse(BaseModel):
    api_base_url: str
    api_key: str
    model: str
    is_configured: bool


def load_config() -> dict:
    """加载配置（自动解密 API Key）"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 解密 API Key
        if 'api_key' in config and config['api_key']:
            config['api_key'] = decrypt_api_key(config['api_key'])
        return config
    return {
        "api_base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini"
    }


def save_config(config: dict):
    """保存配置（自动加密 API Key）"""
    config_to_save = config.copy()
    # 加密 API Key
    if 'api_key' in config_to_save and config_to_save['api_key']:
        config_to_save['api_key'] = encrypt_api_key(config_to_save['api_key'])
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_to_save, f, ensure_ascii=False, indent=2)


def mask_key(key: str) -> str:
    """对 API Key 进行脱敏处理"""
    if not key or len(key) <= 8:
        return key
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


@router.get("", response_model=ConfigResponse)
async def get_config():
    """获取当前配置（API Key 脱敏）"""
    config = load_config()
    return ConfigResponse(
        api_base_url=config.get("api_base_url", ""),
        api_key=mask_key(config.get("api_key", "")),
        model=config.get("model", ""),
        is_configured=bool(config.get("api_key"))
    )


@router.post("", response_model=ConfigResponse)
async def save_config_api(request: ConfigRequest):
    """保存配置"""
    # 获取当前配置
    current_config = load_config()
    
    # 如果 api_key 是 "__KEEP__"，表示保留原来的 Key
    api_key = request.api_key
    if api_key == "__KEEP__":
        api_key = current_config.get("api_key", "")
    
    config = {
        "api_base_url": request.api_base_url,
        "api_key": api_key,
        "model": request.model
    }
    save_config(config)
    
    # 更新运行时配置
    from app.config import settings
    settings.ai_api_base_url = request.api_base_url
    settings.ai_api_key = api_key
    settings.ai_model = request.model
    
    # 刷新 AI 服务客户端
    if api_key:
        try:
            from app.services.ai_service import ai_service
            ai_service.refresh_client()
        except Exception as e:
            print(f"刷新 AI 服务失败: {e}")
    
    return ConfigResponse(
        api_base_url=request.api_base_url,
        api_key=mask_key(api_key),
        model=request.model,
        is_configured=bool(api_key)
    )


@router.get("/status")
async def get_config_status():
    """获取配置状态"""
    config = load_config()
    return {
        "is_configured": bool(config.get("api_key")),
        "model": config.get("model", "")
    }


@router.post("/test")
async def test_ai_connection():
    """测试 AI 连接"""
    config = load_config()
    
    if not config.get("api_key"):
        return {
            "success": False,
            "message": "未配置 API Key"
        }
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("api_base_url", "https://api.openai.com/v1")
        )
        
        # 发送测试请求
        response = client.chat.completions.create(
            model=config.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "user", "content": "Hi"}
            ],
            max_tokens=10
        )
        
        return {
            "success": True,
            "message": f"连接成功！模型: {config.get('model')}",
            "response": response.choices[0].message.content
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)}"
        }
