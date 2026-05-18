"""
config.py - 环境变量配置管理
使用 Pydantic Settings，从 .env 文件读取配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """应用全局配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 忽略 .env 中未定义的字段
    )

    # --- 数据库 ---
    database_url: str = "sqlite+aiosqlite:///./chui_chui_xia.db"  # 默认 SQLite（Railway 生产环境）

    # --- Supabase (可选，用作 PostgreSQL 连接器) ---
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_service_key: Optional[str] = None

    # --- JWT ---
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200  # 30天

    # --- DeepSeek AI API ---
    deepseek_api_key: str = ""
    ai_model: str = "deepseek-chat"

    # --- 微信公众号 (可选) ---
    wechat_app_id: Optional[str] = None
    wechat_app_secret: Optional[str] = None
    wechat_template_id: Optional[str] = None

    # --- 邮件 ---
    mailgun_api_key: Optional[str] = None
    mail_from: str = "noreply@chui-chui-xia.com"

    # --- Sentry ---
    sentry_dsn: Optional[str] = None

    # --- 环境 ---
    env: str = "development"


settings = Settings()
