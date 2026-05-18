"""
api/clients.py - 客户管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from database import get_db
from models.user import User
from models.client import Client
from api.auth import get_current_user


router = APIRouter(prefix="/api/clients", tags=["客户管理"])


# ==================== Schemas ====================

class ClientCreate(BaseModel):
    name: str = Field(max_length=200)
    company: Optional[str] = None
    wechat: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    client_type: str = "old"        # new / old / vip
    payment_habit: str = "normal"    # punctual / normal / often_late
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    wechat: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    client_type: Optional[str] = None
    payment_habit: Optional[str] = None
    notes: Optional[str] = None


class InvoiceRef(BaseModel):
    id: int
    title: str
    amount: int
    status: str
    due_date: datetime

    class Config:
        from_attributes = True


class ClientResponse(BaseModel):
    id: int
    name: str
    company: Optional[str]
    wechat: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    client_type: str
    payment_habit: str
    total_invoiced: int
    total_paid: int
    invoice_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ClientDetailResponse(ClientResponse):
    recent_invoices: List[InvoiceRef]


# ==================== API ====================

@router.get("", response_model=List[ClientResponse])
async def list_clients(
    search: Optional[str] = Query(None, description="搜索客户名/公司名"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取客户列表"""
    query = select(Client).where(Client.user_id == current_user.id)

    if search:
        query = query.where(
            Client.name.ilike(f"%{search}%") | Client.company.ilike(f"%{search}%")
        )

    query = query.order_by(Client.created_at.desc())
    result = await db.execute(query)
    clients = result.scalars().all()
    return [ClientResponse.model_validate(c) for c in clients]


@router.get("/{client_id}", response_model=ClientDetailResponse)
async def get_client(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取客户详情（含最近账款）"""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id, Client.user_id == current_user.id
        ).options(selectinload(Client.invoices))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    from models.invoice import Invoice
    recent = sorted(client.invoices, key=lambda x: x.created_at, reverse=True)[:5]

    return ClientDetailResponse(
        id=client.id, name=client.name, company=client.company,
        wechat=client.wechat, email=client.email, phone=client.phone,
        client_type=client.client_type, payment_habit=client.payment_habit,
        total_invoiced=client.total_invoiced, total_paid=client.total_paid,
        invoice_count=client.invoice_count, created_at=client.created_at,
        recent_invoices=[
            InvoiceRef(id=i.id, title=i.title, amount=i.amount, status=i.status, due_date=i.due_date)
            for i in recent
        ],
    )


@router.post("", response_model=ClientResponse, status_code=201)
async def create_client(
    data: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加客户"""
    # 数量限制
    result = await db.execute(
        select(func.count(Client.id)).where(Client.user_id == current_user.id)
    )
    count = result.scalar()
    if count >= current_user.max_clients and not current_user.is_pro:
        raise HTTPException(status_code=403, detail=f"免费版最多 {current_user.max_clients} 个客户")

    client = Client(user_id=current_user.id, **data.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新客户"""
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.user_id == current_user.id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    await db.commit()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除客户（会同时删除关联账款）"""
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.user_id == current_user.id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")

    await db.delete(client)
    await db.commit()
