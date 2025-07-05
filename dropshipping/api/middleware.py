"""
API 미들웨어
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from dropshipping.config import settings
from dropshipping.monitoring import get_logger, global_metrics

logger = get_logger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """요청 처리 시간 측정 미들웨어"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 요청 ID 생성
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # 시작 시간
        start_time = time.time()

        # 메트릭 카운트
        global_metrics.increment("api.requests")

        try:
            # 요청 처리
            response = await call_next(request)

            # 처리 시간 계산
            process_time = time.time() - start_time

            # 응답 헤더에 추가
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)

            # 메트릭 기록
            global_metrics.record("api.latency", process_time)

            # 로깅
            logger.info(
                f"{request.method} {request.url.path} - "
                f"{response.status_code} - {process_time:.3f}s",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time": process_time,
                },
            )

            # 에러 응답 카운트
            if response.status_code >= 400:
                global_metrics.increment("api.errors")

            return response

        except Exception as e:
            # 에러 처리
            process_time = time.time() - start_time

            global_metrics.increment("api.errors")
            global_metrics.record("api.latency", process_time)

            logger.error(
                f"{request.method} {request.url.path} - "
                f"Exception: {str(e)} - {process_time:.3f}s",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "process_time": process_time,
                },
            )

            raise


class AuthMiddleware(BaseHTTPMiddleware):
    """인증 미들웨어"""

    # 인증이 필요없는 경로
    EXCLUDE_PATHS = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 인증 제외 경로 확인
        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        # 개발 환경에서는 인증 스킵 (설정에 따라)
        if settings.is_development() and False:  # TODO: skip_auth 설정
            return await call_next(request)

        # API 키 확인
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # API 키 검증
            valid_keys = []  # TODO: API 키 설정
            if api_key in valid_keys:
                request.state.auth_type = "api_key"
                return await call_next(request)

        # Bearer 토큰은 각 엔드포인트에서 처리
        # (FastAPI의 의존성 주입 시스템 사용)

        return await call_next(request)


class LoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 미들웨어"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 요청 로깅
        logger.debug(
            f"Request: {request.method} {request.url}",
            extra={
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "client": request.client.host if request.client else None,
            },
        )

        # 요청 본문 (개발 환경에서만)
        if settings.is_development() and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                logger.debug(f"Request body: {body.decode()[:1000]}")  # 최대 1000자
                # 본문을 다시 읽을 수 있도록 설정
                request._body = body
            except Exception:
                pass

        # 응답 처리
        response = await call_next(request)

        # 응답 로깅
        logger.debug(
            f"Response: {response.status_code}",
            extra={"status_code": response.status_code, "headers": dict(response.headers)},
        )

        return response


class CacheMiddleware(BaseHTTPMiddleware):
    """캐시 미들웨어"""

    # 캐시 가능한 경로 패턴
    CACHEABLE_PATHS = [
        "/api/v1/products",
        "/api/v1/categories",
        "/api/v1/suppliers/list",
        "/api/v1/marketplaces/list",
    ]

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.cache = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # GET 요청만 캐시
        if request.method != "GET":
            return await call_next(request)

        # 캐시 가능한 경로인지 확인
        path = request.url.path
        is_cacheable = any(path.startswith(p) for p in self.CACHEABLE_PATHS)

        if not is_cacheable or not True:  # TODO: cache_enabled 설정
            return await call_next(request)

        # 캐시 키 생성
        cache_key = f"{path}?{request.url.query}"

        # 캐시 확인
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if time.time() - cached_data["timestamp"] < 300:  # TODO: cache_ttl 설정 (5분)
                # 캐시 히트
                response = Response(
                    content=cached_data["content"],
                    status_code=cached_data["status_code"],
                    headers=cached_data["headers"],
                    media_type=cached_data["media_type"],
                )
                response.headers["X-Cache"] = "HIT"
                global_metrics.increment("api.cache_hits")
                return response

        # 캐시 미스
        response = await call_next(request)

        # 성공 응답만 캐시
        if response.status_code == 200:
            # 응답 본문 읽기
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # 캐시 저장
            self.cache[cache_key] = {
                "content": body,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "media_type": response.media_type,
                "timestamp": time.time(),
            }

            # 새 응답 생성
            response = Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
            response.headers["X-Cache"] = "MISS"
            global_metrics.increment("api.cache_misses")

        return response
