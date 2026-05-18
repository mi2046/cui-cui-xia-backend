"""
api/reminders.py - 提醒设置 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import get_db
from models.user import User
from models.reminder import ReminderSetting
from api.auth import get_current_user


router = APIRouter(prefix="/api/reminders", tags=["提醒设置"])


class ReminderSettingUpdate(BaseModel):
    enabled: Optional[bool] = None
    reminder_schedule: Optional[List[dict]] = None
    default_tone: Optional[str] = None
    notify_wechat: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_in_app: Optional[bool] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None


class ReminderSettingResponse(BaseModel):
    enabled: bool
    reminder_schedule: Optional[List[dict]]
    default_tone: str
    notify_wechat: bool
    notify_email: bool
    notify_in_app: bool
    quiet_hours_start: Optional[int]
    quiet_hours_end: Optional[int]

    class Config:
        from_attributes = True


@router.get("/settings", response_model=ReminderSettingResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的提醒设置"""
    result = await db.execute(
        select(ReminderSetting).where(ReminderSetting.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        # 返回默认设置
        return ReminderSettingResponse(
            enabled=True,
            reminder_schedule=[
                {"days": -3, "tone": "friendly", "label": "到期前3天"},
                {"days": 0, "tone": "friendly", "label": "到期当天"},
                {"days": 3, "tone": "formal", "label": "逾期3天"},
                {"days": 7, "tone": "formal", "label": "逾期7天"},
                {"days": 14, "tone": "firm", "label": "逾期14天"},
                {"days": 30, "tone": "firm", "label": "逾期30天"},
            ],
            default_tone="friendly",
            notify_wechat=False,
            notify_email=True,
            notify_in_app=True,
            quiet_hours_start=None,
            quiet_hours_end=None,
        )

    return ReminderSettingResponse(
        enabled=settings.enabled,
        reminder_schedule=settings.reminder_schedule,
        default_tone=settings.default_tone,
        notify_wechat=settings.notify_wechat,
        notify_email=settings.notify_email,
        notify_in_app=settings.notify_in_app,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
    )


@router.put("/settings", response_model=ReminderSettingResponse)
async def update_settings(
    data: ReminderSettingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新提醒设置"""
    result = await db.execute(
        select(ReminderSetting).where(ReminderSetting.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = ReminderSetting(user_id=current_user.id)
        db.add(settings)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    return ReminderSettingResponse(
        enabled=settings.enabled,
        reminder_schedule=settings.reminder_schedule,
        default_tone=settings.default_tone,
        notify_wechat=settings.notify_wechat,
        notify_email=settings.notify_email,
        notify_in_app=settings.notify_in_app,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
    )
