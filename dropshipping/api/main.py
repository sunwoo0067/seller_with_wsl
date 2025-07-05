"""
API 서버 메인 애플리케이션
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dropshipping.config import settings
from dropshipping.monitoring import alert_manager, get_logger, global_metrics, setup_logging
from dropshipping.scheduler.main import MainScheduler
from dropshipping.storage.supabase_storage import SupabaseStorage

from .dependencies import get_storage
from .middleware import AuthMiddleware, TimingMiddleware
from .routers import marketplaces, monitoring, orders, products, sourcing, suppliers

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    logger.info("API 서버 시작")

    # 로깅 설정
    setup_logging(
        log_level=settings.log_level,
        log_file=settings.log_file,
        json_logs=settings.env == "production",
    )

    # 알림 매니저 시작
    try:
        alert_manager.start()
    except Exception as e:
        logger.warning(f"알림 매니저 시작 실패: {e}")

    # 스케줄러 시작 (설정된 경우)
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = MainScheduler()
        scheduler.start()
        logger.info("스케줄러 시작됨")

    # 스토리지 초기화 (TODO: SupabaseStorage 구현 완료 후 활성화)
    # app.state.storage = SupabaseStorage()
    app.state.storage = None  # 임시

    yield

    # 종료 시
    logger.info("API 서버 종료")

    # 알림 매니저 종료
    await alert_manager.stop()

    # 스케줄러 종료
    if scheduler:
        scheduler.shutdown()


# FastAPI 앱 생성
app = FastAPI(
    title="드랍쉬핑 자동화 시스템 API",
    description="공급사 상품 수집부터 마켓플레이스 등록까지 전체 워크플로우 자동화",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 미들웨어 설정
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 환경변수에서 가져오기
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted Host (프로덕션에서만)
if settings.is_production():
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])  # TODO: 환경변수에서 가져오기

# GZip 압축
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 커스텀 미들웨어
app.add_middleware(TimingMiddleware)
app.add_middleware(AuthMiddleware)

# 라우터 등록
app.include_router(products.router, prefix="/api/v1/products", tags=["products"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(suppliers.router, prefix="/api/v1/suppliers", tags=["suppliers"])
app.include_router(marketplaces.router, prefix="/api/v1/marketplaces", tags=["marketplaces"])
app.include_router(sourcing.router, prefix="/api/v1/sourcing", tags=["sourcing"])
app.include_router(monitoring.router, prefix="/api/v1/monitoring", tags=["monitoring"])


# 예외 처리
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 예외 처리"""
    global_metrics.increment("api.errors")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.status_code, "message": exc.detail, "path": str(request.url.path)}
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """검증 오류 처리"""
    global_metrics.increment("api.validation_errors")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": 422, "message": "Validation Error", "details": exc.errors()}},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """일반 예외 처리"""
    global_metrics.increment("api.errors")

    logger.exception(f"처리되지 않은 예외: {exc}")

    # 알림 전송
    await alert_manager.send(
        title="API 서버 오류",
        message=f"처리되지 않은 예외 발생: {str(exc)}",
        level="error",
        source="api.exception",
        metadata={"path": str(request.url.path), "method": request.method},
        error=exc,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": 500, "message": "Internal Server Error"}},
    )


# 루트 엔드포인트
@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "name": "드랍쉬핑 자동화 시스템 API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.env,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check(storage: SupabaseStorage = Depends(get_storage)):
    """헬스 체크"""
    try:
        # 데이터베이스 연결 확인
        stats = await storage.get_stats("products")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"DB 헬스 체크 실패: {e}")
        db_status = "unhealthy"

    # 메트릭 요약
    metrics = global_metrics.get_summary()

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "checks": {
            "database": db_status,
            "scheduler": "healthy" if settings.scheduler_enabled else "disabled",
            "monitoring": "healthy",
        },
        "metrics": {
            "api_requests": metrics["system"]["api"]["total_requests"],
            "api_errors": metrics["system"]["api"]["total_errors"],
            "products_processed": metrics["business"]["products"]["processed"],
        },
    }


# CLI 실행을 위한 메인 함수
def run():
    """API 서버 실행"""
    import uvicorn

    host = "0.0.0.0"  # TODO: 환경변수에서 가져오기
    port = 8000  # TODO: 환경변수에서 가져오기

    logger.info(f"API 서버 시작: http://{host}:{port}")

    uvicorn.run(
        "dropshipping.api.main:app",
        host=host,
        port=port,
        reload=settings.is_development(),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
