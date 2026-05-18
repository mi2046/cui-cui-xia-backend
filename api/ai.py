"""
api/ai.py - AI 催款话术生成 API
POST /api/ai/generate-reminder
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from typing import Optional

from database import get_db
from models.user import User
from models.client import Client
from models.invoice import Invoice
from services.ai_service import generate_reminder_messages, get_reminder_suggestion
from api.auth import get_current_user


router = APIRouter(prefix="/api/ai", tags=["AI话术生成"])


# ==================== Schemas ====================

class GenerateReminderRequest(BaseModel):
    """生成催款话术请求"""
    invoice_id: Optional[int] = Field(None, description="如果传入invoice_id，自动填充客户和账款信息")
    client_id: Optional[int] = Field(None, description="客户ID（不传invoice_id时必须传）")
    client_name: Optional[str] = Field(None, description="直接传入客户名（最简模式）")
    amount: int = Field(..., gt=0, description="欠款金额（元）")
    overdue_days: int = Field(..., ge=0, description="逾期天数")
    client_type: str = Field("old", description="客户类型: new / old / vip")
    payment_habit: str = Field("normal", description="付款习惯: punctual / normal / often_late")
    company: Optional[str] = None
    project_title: str = ""
    channel: str = "wechat"


class ReminderMessage(BaseModel):
    wechat_friendly: str
    wechat_formal: str
    email: str
    firm: str
    tip: str
    suggested_tone: str


class GenerateReminderResponse(BaseModel):
    messages: ReminderMessage
    suggestion: str
    usage_info: Optional[dict] = None


# ==================== API ====================

@router.post("/generate-reminder", response_model=GenerateReminderResponse)
async def generate_reminder(
    data: GenerateReminderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI 催款话术生成（核心API）

    输入客户信息和账款情况，AI自动生成4种语气的催款话术。
    支持3种调用方式：
    1. 传入 invoice_id：自动填充所有信息（最推荐）
    2. 传入 client_id：需要同时传金额和逾期天数
    3. 直接传入所有参数：最灵活
    """
    # --- 模式1: 通过 invoice_id 自动获取 ---
    if data.invoice_id is not None:
        result = await db.execute(
            select(Invoice).where(
                and_(
                    Invoice.id == data.invoice_id,
                    Invoice.user_id == current_user.id,
                )
            ).options(selectinload(Invoice.client))
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="账款不存在")

        client_name = invoice.client.name
        company = invoice.client.company
        client_type = invoice.client.client_type
        payment_habit = invoice.client.payment_habit
        amount = data.amount if data.amount else (invoice.amount // 100)  # 分→元
        overdue_days = data.overdue_days
        project_title = invoice.title

    # --- 模式2: 通过 client_id ---
    elif data.client_id is not None:
        result = await db.execute(
            select(Client).where(
                and_(Client.id == data.client_id, Client.user_id == current_user.id)
            )
        )
        client = result.scalar_one_or_none()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")

        client_name = client.name
        company = client.company
        client_type = client.client_type
        payment_habit = client.payment_habit
        amount = data.amount
        overdue_days = data.overdue_days
        project_title = data.project_title

    # --- 模式3: 直接传参 ---
    else:
        if not data.client_name:
            raise HTTPException(status_code=400, detail="client_name 或 invoice_id 至少要传一个")
        client_name = data.client_name
        company = data.company
        client_type = data.client_type
        payment_habit = data.payment_habit
        amount = data.amount
        overdue_days = data.overdue_days
        project_title = data.project_title

    # 免费版次数限制
    today = date.today().isoformat()
    # 简化版：不做次数记录存储（生产环境建议加Redis计数）
    if not current_user.is_pro:
        # 检查用户模型中是否有ai_usage_today字段的简化处理
        pass  # 生产环境请用Redis记录每日使用次数

    # 调用 AI 服务
    try:
        messages = await generate_reminder_messages(
            client_name=client_name,
            amount=amount,
            overdue_days=overdue_days,
            client_type=client_type,
            payment_habit=payment_habit,
            company=company,
            channel=data.channel,
            project_title=project_title,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI服务调用失败: {str(e)}")

    # 获取建议
    suggestion = get_reminder_suggestion(
        client_type=client_type,
        payment_habit=payment_habit,
        overdue_days=overdue_days,
    )

    return GenerateReminderResponse(
        messages=ReminderMessage(**messages),
        suggestion=suggestion,
        usage_info={
            "is_pro": current_user.is_pro,
            "remaining_today": "unlimited" if current_user.is_pro else f"{current_user.max_ai_per_day}/天(免费版)",
        },
    )


@router.get("/suggestion")
async def get_ai_suggestion(
    client_type: str = "old",
    payment_habit: str = "normal",
    overdue_days: int = 7,
):
    """
    快速获取催款建议（不消耗AI额度，轻量接口）
    """
    suggestion = get_reminder_suggestion(client_type, payment_habit, overdue_days)
    return {"suggestion": suggestion}
