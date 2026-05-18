"""
api/invoices.py - 账款管理 API
创建 / 查询 / 更新 / 删除账款，标记已收清
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Optional, List
from database import get_db
from models.user import User
from models.invoice import Invoice, InvoiceStatus
from models.client import Client
from api.auth import get_current_user


router = APIRouter(prefix="/api/invoices", tags=["账款管理"])


# ==================== Pydantic Schemas ====================

class InvoiceCreate(BaseModel):
    client_id: int
    title: str = Field(max_length=500)
    description: Optional[str] = None
    amount: int = Field(gt=0, description="金额(分)，如5000表示50元")
    due_date: datetime
    status: str = InvoiceStatus.DRAFT.value


class InvoiceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[int] = Field(default=None, gt=0)
    due_date: Optional[datetime] = None
    status: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: int
    client_id: int
    client_name: str
    company: Optional[str]
    title: str
    description: Optional[str]
    amount: int
    paid_amount: int
    due_date: datetime
    status: str
    reminder_count: int
    last_reminder_at: Optional[datetime]
    paid_at: Optional[datetime]
    created_at: datetime
    overdue_days: int = 0  # 计算字段

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    total: int
    pending: int
    overdue: int
    paid: int
    invoices: List[InvoiceResponse]


class StatsResponse(BaseModel):
    total_pending: int       # 待收总额(分)
    total_overdue: int       # 逾期总额(分)
    pending_count: int
    overdue_count: int
    paid_count: int
    total_paid_this_month: int


# ==================== API 路由 ====================

def _calc_overdue_days(due_date: datetime, status: str) -> int:
    if status in (InvoiceStatus.PAID.value,):
        return 0
    delta = datetime.utcnow() - due_date
    return max(0, delta.days)


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    status: Optional[str] = Query(None, description="筛选状态: draft/sent/overdue/paid"),
    client_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取账款列表"""
    query = select(Invoice).where(Invoice.user_id == current_user.id).options(
        selectinload(Invoice.client)
    )

    if status:
        query = query.where(Invoice.status == status)
    if client_id:
        query = query.where(Invoice.client_id == client_id)

    query = query.order_by(
        case(
            (Invoice.status == InvoiceStatus.OVERDUE.value, 0),
            (Invoice.status == InvoiceStatus.SENT.value, 1),
            (Invoice.status == InvoiceStatus.DRAFT.value, 2),
            else_=3,
        ),
        Invoice.due_date.asc(),
    )

    result = await db.execute(query)
    invoices = result.scalars().all()

    now = datetime.utcnow()
    responses = []
    pending = overdue = paid = 0

    for inv in invoices:
        # 实时计算逾期状态
        if inv.status not in (InvoiceStatus.PAID.value, InvoiceStatus.DRAFT.value):
            if inv.due_date < now and inv.status != InvoiceStatus.PAID.value:
                actual_status = InvoiceStatus.OVERDUE.value
            else:
                actual_status = inv.status
        else:
            actual_status = inv.status

        overdue_days = _calc_overdue_days(inv.due_date, actual_status)

        responses.append(InvoiceResponse(
            id=inv.id,
            client_id=inv.client_id,
            client_name=inv.client.name,
            company=inv.client.company,
            title=inv.title,
            description=inv.description,
            amount=inv.amount,
            paid_amount=inv.paid_amount,
            due_date=inv.due_date,
            status=actual_status,
            reminder_count=inv.reminder_count,
            last_reminder_at=inv.last_reminder_at,
            paid_at=inv.paid_at,
            created_at=inv.created_at,
            overdue_days=overdue_days,
        ))

        if actual_status == InvoiceStatus.PAID.value:
            paid += 1
        elif actual_status == InvoiceStatus.OVERDUE.value:
            overdue += 1
        else:
            pending += 1

    return InvoiceListResponse(
        total=len(invoices),
        pending=pending,
        overdue=overdue,
        paid=paid,
        invoices=responses,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_invoice_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取账款统计（首页数据卡片）"""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(Invoice).where(Invoice.user_id == current_user.id)
    )
    invoices = result.scalars().all()

    total_pending = total_overdue = pending_c = overdue_c = paid_c = 0
    total_paid_month = 0

    for inv in invoices:
        if inv.status == InvoiceStatus.PAID.value:
            paid_c += 1
            if inv.paid_at and inv.paid_at >= month_start:
                total_paid_month += inv.paid_amount
        elif inv.due_date < now and inv.status != InvoiceStatus.PAID.value:
            total_overdue += inv.amount - inv.paid_amount
            overdue_c += 1
        else:
            total_pending += inv.amount - inv.paid_amount
            pending_c += 1

    return StatsResponse(
        total_pending=total_pending,
        total_overdue=total_overdue,
        pending_count=pending_c,
        overdue_count=overdue_c,
        paid_count=paid_c,
        total_paid_this_month=total_paid_month,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个账款详情"""
    result = await db.execute(
        select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.user_id == current_user.id)
        ).options(selectinload(Invoice.client))
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="账款不存在")

    now = datetime.utcnow()
    actual_status = inv.status
    if inv.status != InvoiceStatus.PAID.value and inv.due_date < now:
        actual_status = InvoiceStatus.OVERDUE.value

    return InvoiceResponse(
        id=inv.id,
        client_id=inv.client_id,
        client_name=inv.client.name,
        company=inv.client.company,
        title=inv.title,
        description=inv.description,
        amount=inv.amount,
        paid_amount=inv.paid_amount,
        due_date=inv.due_date,
        status=actual_status,
        reminder_count=inv.reminder_count,
        last_reminder_at=inv.last_reminder_at,
        paid_at=inv.paid_at,
        created_at=inv.created_at,
        overdue_days=_calc_overdue_days(inv.due_date, actual_status),
    )


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建账款"""
    # 验证客户归属
    result = await db.execute(
        select(Client).where(
            and_(Client.id == data.client_id, Client.user_id == current_user.id)
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 免费版客户数量限制
    result2 = await db.execute(
        select(func.count(Client.id)).where(Client.user_id == current_user.id)
    )
    client_count = result2.scalar()
    if client_count >= current_user.max_clients and not current_user.is_pro:
        raise HTTPException(status_code=403, detail=f"免费版最多 {current_user.max_clients} 个客户，请升级Pro版")

    invoice = Invoice(
        user_id=current_user.id,
        client_id=data.client_id,
        title=data.title,
        description=data.description,
        amount=data.amount,
        due_date=data.due_date,
        status=data.status,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # 更新客户统计数据
    client.total_invoiced += data.amount
    client.invoice_count += 1
    await db.commit()

    return InvoiceResponse(
        id=invoice.id,
        client_id=invoice.client_id,
        client_name=client.name,
        company=client.company,
        title=invoice.title,
        description=invoice.description,
        amount=invoice.amount,
        paid_amount=0,
        due_date=invoice.due_date,
        status=invoice.status,
        reminder_count=0,
        last_reminder_at=None,
        paid_at=None,
        created_at=invoice.created_at,
        overdue_days=0,
    )


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新账款"""
    result = await db.execute(
        select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.user_id == current_user.id)
        ).options(selectinload(Invoice.client))
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="账款不存在")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)

    await db.commit()
    await db.refresh(inv)

    return InvoiceResponse(
        id=inv.id,
        client_id=inv.client_id,
        client_name=inv.client.name,
        company=inv.client.company,
        title=inv.title,
        description=inv.description,
        amount=inv.amount,
        paid_amount=inv.paid_amount,
        due_date=inv.due_date,
        status=inv.status,
        reminder_count=inv.reminder_count,
        last_reminder_at=inv.last_reminder_at,
        paid_at=inv.paid_at,
        created_at=inv.created_at,
        overdue_days=_calc_overdue_days(inv.due_date, inv.status),
    )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除账款"""
    result = await db.execute(
        select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.user_id == current_user.id)
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="账款不存在")

    await db.delete(inv)
    await db.commit()


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
async def mark_invoice_paid(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记账款为已收清"""
    result = await db.execute(
        select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.user_id == current_user.id)
        ).options(selectinload(Invoice.client))
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="账款不存在")

    inv.status = InvoiceStatus.PAID.value
    inv.paid_amount = inv.amount
    inv.paid_at = datetime.utcnow()

    # 更新客户统计数据
    inv.client.total_paid += inv.amount

    await db.commit()
    await db.refresh(inv)

    return InvoiceResponse(
        id=inv.id, client_id=inv.client_id,
        client_name=inv.client.name, company=inv.client.company,
        title=inv.title, description=inv.description,
        amount=inv.amount, paid_amount=inv.paid_amount,
        due_date=inv.due_date, status=inv.status,
        reminder_count=inv.reminder_count, last_reminder_at=inv.last_reminder_at,
        paid_at=inv.paid_at, created_at=inv.created_at, overdue_days=0,
    )
