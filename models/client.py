"""
models/client.py - 客户模型
"""
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from database import Base


class Client(Base):
    """客户（付款方）"""
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # 基本信息
    name: Mapped[str] = mapped_column(String(200), nullable=False)         # 客户名称
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 公司名称
    wechat: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # 微信号
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # 客户类型 (用于AI话术生成)
    client_type: Mapped[str] = mapped_column(String(20), default="old")  # new / old / vip
    payment_habit: Mapped[str] = mapped_column(String(20), default="normal")  # punctual / normal / often_late

    # 备注
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 统计数据 (自动计算)
    total_invoiced: Mapped[int] = mapped_column(Integer, default=0)    # 历史累计发票金额(分)
    total_paid: Mapped[int] = mapped_column(Integer, default=0)         # 历史累计已收金额(分)
    invoice_count: Mapped[int] = mapped_column(Integer, default=0)      # 历史合作次数

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="clients")
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")
