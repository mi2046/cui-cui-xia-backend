"""
main.py - FastAPI 应用入口
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import init_db
from api import auth, invoices, clients, ai, reminders
from services.reminder_scheduler import start_scheduler, stop_scheduler

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO if settings.env == "development" else logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期：启动 → 运行 → 关闭"""
    # 启动时
    logger.info("🚀 催催侠后端启动中...")
    await init_db()  # 创建数据库表
    start_scheduler()  # 启动定时任务
    logger.info("✅ 催催侠后端已就绪!")

    yield  # 应用运行中...

    # 关闭时
    stop_scheduler()
    logger.info("👋 催催侠后端已关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="催催侠 API",
    description="AI智能催款工具后端 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.env == "development" else None,  # 生产环境关闭文档
    redoc_url="/redoc" if settings.env == "development" else None,
)


# ==================== CORS 中间件 ====================
# 允许微信小程序和前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 全局异常处理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    logger.error(f"未处理异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"错误: {type(exc).__name__}: {str(exc)}", "trace": traceback.format_exc()[-500:]},
    )


# ==================== 注册路由 ====================

app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(clients.router)
app.include_router(ai.router)
app.include_router(reminders.router)


# ==================== 健康检查 ====================

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "催催侠", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "message": "🎯 催催侠 API",
        "docs": "/docs" if settings.env == "development" else "生产环境文档已关闭",
        "version": "1.0.0",
    }


# ==================== 启动命令 ====================
# 开发环境运行: uvicorn main:app --reload --port 8000
# 生产环境运行: uvicorn main:app --host 0.0.0.0 --port 8000
