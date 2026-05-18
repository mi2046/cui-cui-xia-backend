"""
models/invoice.py - 账款/发票模型
"""
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Date, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from database import Base
import enum


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"           # 草稿
    SENT = "sent"             # 已发送
    OVERDUE = "overdue"       # 已逾期
    PARTIAL = "partial"        # 部分付款
    PAID = "paid"             # 已结清


class Invoice(Base):
    """账款（应收账款）"""
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False)

    # 金额 (单位：分，避免浮点精度问题)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)          # 账单总金额(分)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)          # 已付金额(分)

    # 项目信息
    title: Mapped[str] = mapped_column(String(500), nullable=False)        # 账单标题/项目名
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 项目描述

    # 日期
    issue_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # 开票日期
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)    # 到期日期

    # 状态
    status: Mapped[str] = mapped_column(String(20), default=InvoiceStatus.DRAFT.value)

    # AI生成的话术历史
    ai_generated_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON数组

    # 提醒状态
    last_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)       # 已发送提醒次数

    # 标记收款
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="invoices")
    client: Mapped["Client"] = relationship("Client", back_populates="invoices")
