"""
API 의존성 주입
"""

from datetime import datetime, timedelta
from typing import Annotated, Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dropshipping.config import settings
from dropshipping.monitoring import get_logger
from dropshipping.storage.base import BaseStorage

logger = get_logger(__name__)

# Bearer 토큰 스키마
security = HTTPBearer()


async def get_storage(request: Request) -> BaseStorage:
    """스토리지 인스턴스 반환"""
    # TODO: 실제 스토리지 반환
    from tests.fixtures.mock_storage import MockStorage

    return MockStorage()


async def get_api_key(api_key: Annotated[Optional[str], Header()] = None) -> Optional[str]:
    """API 키 추출"""
    return api_key


async def verify_api_key(api_key: Optional[str] = Depends(get_api_key)) -> bool:
    """API 키 검증"""
    if not api_key:
        return False

    # TODO: 실제 API 키 검증 로직 구현
    # 임시로 환경 변수의 키와 비교
    valid_keys = []  # TODO: API 키 설정
    return api_key in valid_keys


async def require_api_key(is_valid: bool = Depends(verify_api_key)) -> None:
    """API 키 필수 요구"""
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    storage: BaseStorage = Depends(get_storage),
) -> dict:
    """현재 사용자 정보 반환"""
    token = credentials.credentials

    try:
        # JWT 토큰 디코드
        payload = jwt.decode(token, "your-secret-key", algorithms=["HS256"])  # TODO: 비밀 키 설정

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        # 사용자 정보 조회
        user = await storage.get("users", user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        return user

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """관리자 권한 요구"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


class RateLimiter:
    """요청 속도 제한"""

    def __init__(self, requests: int = 100, window: int = 60):
        self.requests = requests
        self.window = window
        self.cache = {}

    async def __call__(self, request: Request) -> None:
        # 클라이언트 IP 추출
        client_ip = request.client.host
        now = datetime.now()

        # 캐시에서 요청 기록 조회
        if client_ip in self.cache:
            requests_data = self.cache[client_ip]
            # 윈도우 내의 요청만 필터링
            window_start = now - timedelta(seconds=self.window)
            requests_data = [req_time for req_time in requests_data if req_time > window_start]

            # 요청 수 확인
            if len(requests_data) >= self.requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {self.requests} requests per {self.window} seconds",
                )

            requests_data.append(now)
            self.cache[client_ip] = requests_data
        else:
            self.cache[client_ip] = [now]


# 속도 제한 인스턴스
rate_limiter = RateLimiter(requests=100, window=60)


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """액세스 토큰 생성"""
    to_encode = {"user_id": user_id}

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode, settings.config.get("secret_key", "your-secret-key"), algorithm="HS256"
    )

    return encoded_jwt


class Pagination:
    """페이지네이션 파라미터"""

    def __init__(self, page: int = 1, page_size: int = 20, max_page_size: int = 100):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), max_page_size)
        self.offset = (self.page - 1) * self.page_size
        self.limit = self.page_size

    def paginate(self, total: int, items: list) -> dict:
        """페이지네이션 응답 생성"""
        total_pages = (total + self.page_size - 1) // self.page_size

        return {
            "items": items,
            "pagination": {
                "page": self.page,
                "page_size": self.page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": self.page < total_pages,
                "has_prev": self.page > 1,
            },
        }
