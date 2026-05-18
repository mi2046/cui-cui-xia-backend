"""
database.py - 数据库连接管理
支持 SQLite (本地开发) 和 PostgreSQL (生产环境)
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings


# 判断数据库类型
is_sqlite = settings.database_url.startswith("sqlite")

# 创建异步引擎
if is_sqlite:
    # SQLite 异步模式 (aiosqlite)
    engine = create_async_engine(
        settings.database_url,
        echo=settings.env == "development",
        connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    )
else:
    # PostgreSQL (asyncpg)
    connect_args = {}
    if "pooler.supabase.com" in settings.database_url:
        connect_args["server_settings"] = {"project": "gfsppqhuquehyorfhjbn"}
    
    engine = create_async_engine(
        settings.database_url,
        echo=settings.env == "development",
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

# 异步 Session 工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有模型的基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库 Session"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """启动时创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
