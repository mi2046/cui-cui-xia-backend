"""
services/reminder_scheduler.py - 定时催款提醒调度器
使用 APScheduler 定期检查逾期账款并发送提醒
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime, timedelta

from database import async_session
from models.user import User
from models.invoice import Invoice, InvoiceStatus
from models.client import Client
from models.reminder import ReminderSetting


logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")  # 北京时间


async def check_overdue_invoices(db: AsyncSession):
    """
    定时任务：检查所有逾期账款，触发自动提醒
    每天早上9点执行（北京时间）
    """
    now = datetime.utcnow()

    # 找出所有已发送但逾期的账款
    result = await db.execute(
        select(Invoice).where(
            and_(
                Invoice.status.notin_([InvoiceStatus.DRAFT.value, InvoiceStatus.PAID.value]),
                Invoice.due_date < now,
            )
        ).options(
            selectinload(Invoice.user).selectinload(User.reminder_settings),
            selectinload(Invoice.client),
        )
    )
    invoices = result.scalars().all()

    reminded_count = 0
    for invoice in invoices:
        settings = invoice.user.reminder_settings
        if not settings or not settings.enabled:
            continue

        # 检查上次提醒时间，避免重复提醒
        if invoice.last_reminder_at:
            days_since_reminder = (now - invoice.last_reminder_at).days
            # 默认至少间隔3天才再次提醒
            if days_since_reminder < 3:
                continue

        # 计算应使用的话术语气
        overdue_days = (now - invoice.due_date).days

        if overdue_days <= 7:
            tone = "friendly"
        elif overdue_days <= 30:
            tone = "formal"
        else:
            tone = "firm"

        # 构建提醒内容
        message = _build_reminder_message(
            client_name=invoice.client.name,
            amount=invoice.amount // 100,
            overdue_days=overdue_days,
            tone=tone,
            project_title=invoice.title,
        )

        # 发送提醒（根据用户设置的渠道）
        if settings.notify_in_app:
            # 应用内通知，记录到数据库（实际推送由前端轮询）
            invoice.reminder_count += 1
            invoice.last_reminder_at = now
            logger.info(f"[提醒] 向用户{invoice.user_id}发送逾期提醒: {invoice.title}")

        if settings.notify_email and invoice.client.email:
            await _send_email_reminder(
                to=invoice.client.email,
                client_name=invoice.client.name,
                subject=f"催款提醒：{invoice.title} 已逾期{overdue_days}天",
                body=message,
            )

        if settings.notify_wechat:
            # 微信公众号模板消息（需要用户已授权）
            if invoice.client.wechat:
                await _send_wechat_reminder(
                    openid=invoice.client.wechat,
                    message=message,
                )

        reminded_count += 1

    await db.commit()
    logger.info(f"[提醒调度] 检查完成，新增提醒 {reminded_count} 条")


def _build_reminder_message(
    client_name: str,
    amount: int,
    overdue_days: int,
    tone: str,
    project_title: str,
) -> str:
    """构建提醒内容"""
    if tone == "friendly":
        return (
            f"亲爱的{client_name}，您好！\n"
            f"您的项目「{project_title}」尾款{amount}元已逾期{overdue_days}天。"
            f"方便的话这周安排一下？感谢配合🙏"
        )
    elif tone == "formal":
        return (
            f"{client_name}您好：\n"
            f"根据合同约定，项目「{project_title}」尾款{amount}元已逾期{overdue_days}天。"
            f"请尽快安排付款，如有困难请联系我协商解决方案，谢谢！"
        )
    else:
        return (
            f"{client_name}：\n"
            f"项目「{project_title}」尾款{amount}元已逾期{overdue_days}天。"
            f"如本周内仍未收到款项，我方将暂停后续服务，并保留法律追责权利。"
        )


async def _send_email_reminder(to: str, client_name: str, subject: str, body: str):
    """发送邮件提醒（使用 Mailgun）"""
    # TODO: 接入真实邮件服务
    logger.info(f"[邮件] 发送提醒到 {to}: {subject}")


async def _send_wechat_reminder(openid: str, message: str):
    """发送微信模板消息提醒"""
    # TODO: 接入微信公众号模板消息
    logger.info(f"[微信] 发送提醒到 {openid}: {message[:50]}...")


def start_scheduler():
    """启动调度器"""
    scheduler.add_job(
        check_overdue_invoices,
        CronTrigger(hour=9, minute=0, timezone="Asia/Shanghai"),
        args=[async_session],
        id="check_overdue_invoices",
        replace_existing=True,
        misfire_grace_time=3600,  # 最多容忍1小时延迟
    )
    scheduler.start()
    logger.info("[调度器] 已启动，每天早上9点检查逾期账款")


def stop_scheduler():
    """停止调度器"""
    scheduler.shutdown(wait=False)
    logger.info("[调度器] 已停止")
