"""
models/user.py - 用户模型
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from database import Base


class User(Base):
    """应用用户（自由职业者）"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=True)       # 显示名称
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    wechat_openid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 微信登录
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # 会员状态
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 配额 (免费版限制)
    max_clients: Mapped[int] = mapped_column(Integer, default=3)    # 免费版3个客户
    max_ai_per_day: Mapped[int] = mapped_column(Integer, default=5)  # 免费版每天5次

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 开发者免责协议
    agreed_to_disclaimer: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否同意免责协议
    disclaimer_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 同意的协议版本
    disclaimer_agreed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 同意时间

    # 关系
    clients: Mapped[List["Client"]] = relationship("Client", back_populates="user", cascade="all, delete-orphan")
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="user", cascade="all, delete-orphan")
    reminder_settings: Mapped[Optional["ReminderSetting"]] = relationship(
        "ReminderSetting", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
