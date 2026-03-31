"""
FastAPI 主应用入口
Domain Manage API 主模块
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    PlatformAPIError,
)
from app.api.v1 import api_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("Domain Manage API started")
    yield
    # 关闭时执行
    logger.info("Domain Manage API stopped")


app = FastAPI(
    title=settings.APP_NAME,
    description="域名管理平台 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件 - 开发环境允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 异常处理器
@app.exception_handler(PlatformAPIError)
async def platform_api_error_handler(request, exc: PlatformAPIError):
    """平台 API 错误处理器"""
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "code": "PLATFORM_ERROR",
            "message": f"{exc.platform} API 错误: {exc.message}",
            "platform_code": exc.code,
        },
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request, exc: AuthenticationError):
    """认证错误处理器"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "code": "AUTHENTICATION_ERROR",
            "message": str(exc) or "认证失败",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_error_handler(request, exc: PermissionDeniedError):
    """权限不足错误处理器"""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "code": "PERMISSION_DENIED",
            "message": str(exc) or "权限不足",
        },
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request, exc: NotFoundError):
    """资源未找到错误处理器"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "code": "NOT_FOUND",
            "message": str(exc) or "资源不存在",
        },
    )


# 健康检查端点
@app.get("/health", tags=["health"])
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
    }


# 注册 API v1 路由
app.include_router(api_router, prefix="/api/v1")
