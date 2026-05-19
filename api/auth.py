"""
api/auth.py - 认证相关 API
注册 / 登录 / 获取当前用户 / Token 刷新 / 免责协议 / 微信登录
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from database import get_db
from models.user import User
from config import settings
from typing import Optional, List
from services.disclaimer_service import get_disclaimer, validate_agreement
import httpx
import bcrypt as _bcrypt


router = APIRouter(prefix="/api/auth", tags=["认证"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码（兼容新旧哈希格式）"""
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """哈希密码"""
    hashed = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt())
    return hashed.decode("utf-8")


# ==================== Pydantic Schemas ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: Optional[str] = None
    agreed_to_disclaimer: bool = False          # 必须同意免责协议
    disclaimer_version: Optional[str] = None   # 同意的协议版本


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    nickname: Optional[str]
    is_pro: bool
    max_clients: int
    max_ai_per_day: int
    created_at: datetime
    agreed_to_disclaimer: bool
    disclaimer_version: Optional[str]
    disclaimer_agreed_at: Optional[datetime]


class DisclaimerResponse(BaseModel):
    version: str
    effective_date: str
    language: str
    content: str
    total_chars: int


class DisclaimerAgreeRequest(BaseModel):
    agreed: bool
    version: str


class WechatLoginRequest(BaseModel):
    code: str                           # wx.login() 返回的 code
    nickname: Optional[str] = None     # 用户昵称（可选）
    avatar_url: Optional[str] = None   # 用户头像（可选）
    agreed_to_disclaimer: bool = False  # 必须同意免责协议


# ==================== 工具函数 ====================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token 已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


# ==================== 免责协议 API ====================

@router.get("/disclaimer", response_model=DisclaimerResponse)
async def get_disclaimer_text(
    language: str = Query("zh", description="语言：zh=中文，en=英文"),
):
    """
    获取开发者免责协议全文
    用户在注册前必须阅读并同意本协议
    """
    if language not in ("zh", "en"):
        language = "zh"

    return get_disclaimer(language=language)


@router.post("/disclaimer/agree")
async def agree_disclaimer(
    req: DisclaimerAgreeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    已登录用户同意免责协议
    用于用户补签协议（当协议更新后）
    """
    if not req.agreed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须同意免责协议才能使用本服务",
        )

    # 验证协议版本是否有效
    if not validate_agreement(req.version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"协议版本无效，当前版本为 {get_disclaimer('zh')['version']}",
        )

    # 更新用户协议同意状态
    current_user.agreed_to_disclaimer = True
    current_user.disclaimer_version = req.version
    current_user.disclaimer_agreed_at = datetime.utcnow()
    await db.commit()

    return {"message": "协议同意状态已更新", "version": req.version}


# ==================== 认证 API ====================

@router.post("/register", response_model=Token)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    用户注册

    ⚠️ 重要提示：
    注册前必须阅读并同意《开发者服务免责协议》
    AI 生成的话术仅供辅助参考，用户需自行承担使用责任
    """
    # --- 免责协议强制验证 ---
    if not data.agreed_to_disclaimer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "注册前必须同意《开发者服务免责协议》\n\n"
                "请先调用 GET /api/auth/disclaimer 获取协议全文，"
                "然后携带 agreed_to_disclaimer=true 重新提交注册。"
            ),
        )

    # 验证协议版本
    if data.disclaimer_version and not validate_agreement(data.disclaimer_version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"协议版本已过期，请使用最新版本（{get_disclaimer('zh')['version']}）",
        )

    # --- 密码强度验证 ---
    if len(data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少为 8 个字符",
        )

    # --- 邮箱唯一性检查 ---
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已被注册")

    # --- 创建用户 ---
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        nickname=data.nickname or data.email.split("@")[0],
        agreed_to_disclaimer=True,
        disclaimer_version=data.disclaimer_version or get_disclaimer("zh")["version"],
        disclaimer_agreed_at=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # --- 生成 Token ---
    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    用户登录 (OAuth2 Password 模式)

    注意：AI 催款话术仅供辅助参考，使用时请自行判断适当性
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    # 检查免责协议状态（如果协议有更新，提示用户重新同意）
    if not user.agreed_to_disclaimer:
        raise HTTPException(
            status_code=403,
            detail="请先同意《开发者服务免责协议》后再使用本服务",
        )

    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息
    """
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    刷新 Token
    """
    access_token = create_access_token(data={"sub": current_user.id})
    return Token(access_token=access_token)


# ==================== 微信小程序登录 ====================

@router.post("/wechat-login", response_model=Token)
async def wechat_login(
    data: WechatLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    微信小程序登录 / 自动注册

    流程：
    1. 前端调用 wx.login() 获取临时 code
    2. 发送 code 到本接口
    3. 后端用 code + AppID + AppSecret 换取 openid
    4. 根据 openid 查找或创建用户
    5. 返回 JWT Token

    注意：初次使用需要同意免责协议（agreed_to_disclaimer=true）
    """
    # 1. 检查微信配置
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="微信登录未配置，请联系管理员",
        )

    # 2. 用 code 换 openid
    wx_url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "js_code": data.code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(wx_url, params=params)
            wx_data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"微信服务器请求失败: {str(e)}")

    if "errcode" in wx_data and wx_data["errcode"] != 0:
        raise HTTPException(
            status_code=400,
            detail=f"微信登录失败: {wx_data.get('errmsg', '未知错误')} (errcode: {wx_data.get('errcode')})",
        )

    openid: str = wx_data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="微信返回数据异常，缺少 openid")

    # 3. 查找已有用户
    result = await db.execute(select(User).where(User.wechat_openid == openid))
    user = result.scalar_one_or_none()

    if user:
        # 已注册用户 → 直接登录
        if not user.is_active:
            raise HTTPException(status_code=403, detail="账号已被禁用")
        # 更新昵称/头像（如果有传）
        if data.nickname and not user.nickname:
            user.nickname = data.nickname
        if data.avatar_url and not user.avatar_url:
            user.avatar_url = data.avatar_url
        await db.commit()
    else:
        # 新用户 → 自动注册，必须同意免责协议
        if not data.agreed_to_disclaimer:
            raise HTTPException(
                status_code=400,
                detail="首次使用须同意《开发者服务免责协议》，请传入 agreed_to_disclaimer=true",
            )

        # 用 openid 生成唯一邮箱（微信用户无邮箱概念）
        fake_email = f"wx_{openid[:16]}@wechat.local"
        import secrets
        fake_password = secrets.token_hex(32)  # 不可用于登录，仅满足字段非空

        user = User(
            email=fake_email,
            hashed_password=get_password_hash(fake_password),
            nickname=data.nickname or f"微信用户{openid[:6]}",
            avatar_url=data.avatar_url,
            wechat_openid=openid,
            agreed_to_disclaimer=True,
            disclaimer_version=get_disclaimer("zh")["version"],
            disclaimer_agreed_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)

