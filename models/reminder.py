"""
models/reminder.py - 提醒设置模型
"""
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from database import Base


class ReminderSetting(Base):
    """用户的催款提醒全局设置"""
    __tablename__ = "reminder_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)

    # 开关
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 提醒时机配置 (JSON数组)
    # 例如: [{"days": -3, "tone": "friendly"}, {"days": 0, "tone": "friendly"}, {"days": 3, "tone": "formal"}, ...]
    reminder_schedule: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # 默认话术风格
    default_tone: Mapped[str] = mapped_column(String(20), default="friendly")  # friendly / formal / firm

    # 通知渠道
    notify_wechat: Mapped[bool] = mapped_column(Boolean, default=False)   # 微信模板消息
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)      # 邮件
    notify_in_app: Mapped[bool] = mapped_column(Boolean, default=True)     # 应用内通知

    # 高级设置
    quiet_hours_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 几点开始不提醒 (0-23)
    quiet_hours_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # 几点结束

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="reminder_settings")
