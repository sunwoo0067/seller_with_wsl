"""
마켓플레이스 관련 API 엔드포인트
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from dropshipping.api.dependencies import (
    get_current_user,
    get_storage,
    rate_limiter,
    require_api_key,
)
from dropshipping.monitoring import get_logger
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.registry import UploaderRegistry

logger = get_logger(__name__)

router = APIRouter()


@router.get("/list")
async def list_marketplaces(
    storage: BaseStorage = Depends(get_storage), _: None = Depends(rate_limiter)
):
    """등록된 마켓플레이스 목록 조회"""
    try:
        # 레지스트리에서 마켓플레이스 목록 가져오기
        registry = UploaderRegistry()
        marketplaces = []

        for mp_name in registry.list_uploaders():
            mp_info = {
                "name": mp_name,
                "display_name": mp_name.title(),
                "enabled": True,
                "features": [],
            }

            # DB에서 추가 정보 조회
            db_mp = await storage.list("marketplaces", filters={"name": mp_name}, limit=1)

            if db_mp:
                mp_info.update(db_mp[0])

            marketplaces.append(mp_info)

        return {"marketplaces": marketplaces}

    except Exception as e:
        logger.error(f"마켓플레이스 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="마켓플레이스 목록을 조회할 수 없습니다",
        )


@router.get("/{marketplace_name}/info")
async def get_marketplace_info(
    marketplace_name: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """마켓플레이스 상세 정보 조회"""
    try:
        # 레지스트리 확인
        registry = UploaderRegistry()
        if marketplace_name not in registry.list_uploaders():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="마켓플레이스를 찾을 수 없습니다"
            )

        # 업로더 인스턴스 생성
        uploader = registry.get_uploader(marketplace_name)

        # 기본 정보
        info = {
            "name": marketplace_name,
            "display_name": marketplace_name.title(),
            "type": uploader.__class__.__name__,
            "enabled": True,
            "features": getattr(uploader, "features", []),
            "api_version": getattr(uploader, "api_version", "1.0"),
            "rate_limit": getattr(uploader, "rate_limit", None),
            "commission_rate": getattr(uploader, "commission_rate", 0.0),
        }

        # DB에서 추가 정보 조회
        db_mp = await storage.list("marketplaces", filters={"name": marketplace_name}, limit=1)

        if db_mp:
            info.update(db_mp[0])

        # 통계 정보
        product_count = await storage.count(
            "marketplace_products", filters={"marketplace": marketplace_name}
        )

        order_count = await storage.count("orders", filters={"marketplace": marketplace_name})

        info["statistics"] = {
            "total_products": product_count,
            "total_orders": order_count,
            "last_sync": None,  # TODO: 실제 동기화 시간 조회
        }

        return info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"마켓플레이스 정보 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="마켓플레이스 정보를 조회할 수 없습니다",
        )


@router.post("/{marketplace_name}/upload")
async def upload_products(
    marketplace_name: str,
    product_ids: List[str],
    background_tasks: BackgroundTasks,
    account_id: Optional[str] = Query(None, description="특정 계정으로 업로드"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(require_api_key),
):
    """상품 업로드"""
    try:
        # 레지스트리 확인
        registry = UploaderRegistry()
        if marketplace_name not in registry.list_uploaders():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="마켓플레이스를 찾을 수 없습니다"
            )

        # 상품 확인
        products = []
        for product_id in product_ids:
            product = await storage.get("products", product_id)
            if not product:
                logger.warning(f"상품을 찾을 수 없음: {product_id}")
                continue
            products.append(product)

        if not products:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="업로드할 상품이 없습니다"
            )

        # 백그라운드 작업으로 업로드 실행
        async def upload_task():
            try:
                uploader = registry.get_uploader(marketplace_name)
                # TODO: 실제 업로드 로직 구현
                logger.info(f"{marketplace_name}에 {len(products)}개 상품 업로드 시작")

                # 업로드 작업 기록
                await storage.create(
                    "upload_jobs",
                    {
                        "marketplace": marketplace_name,
                        "account_id": account_id,
                        "status": "completed",
                        "total_products": len(products),
                        "successful": len(products),
                        "failed": 0,
                        "started_at": datetime.utcnow().isoformat(),
                        "completed_at": datetime.utcnow().isoformat(),
                    },
                )

            except Exception as e:
                logger.error(f"{marketplace_name} 업로드 실패: {e}")
                await storage.create(
                    "upload_jobs",
                    {
                        "marketplace": marketplace_name,
                        "status": "failed",
                        "error": str(e),
                        "started_at": datetime.utcnow().isoformat(),
                    },
                )

        background_tasks.add_task(upload_task)

        # 작업 ID 생성
        job_id = f"{marketplace_name}_{datetime.utcnow().timestamp()}"

        return {
            "job_id": job_id,
            "marketplace": marketplace_name,
            "product_count": len(products),
            "status": "started",
            "message": "업로드가 백그라운드에서 시작되었습니다",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상품 업로드 시작 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="업로드를 시작할 수 없습니다"
        )


@router.get("/{marketplace_name}/accounts")
async def list_marketplace_accounts(
    marketplace_name: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """마켓플레이스 계정 목록 조회"""
    try:
        # 계정 목록 조회
        accounts = await storage.list(
            "marketplace_accounts", filters={"marketplace": marketplace_name}
        )

        return {"marketplace": marketplace_name, "accounts": accounts}

    except Exception as e:
        logger.error(f"계정 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="계정 목록을 조회할 수 없습니다",
        )


@router.post("/{marketplace_name}/accounts")
async def create_marketplace_account(
    marketplace_name: str,
    account_data: Dict[str, Any],
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user),
):
    """마켓플레이스 계정 추가"""
    try:
        # 레지스트리 확인
        registry = UploaderRegistry()
        if marketplace_name not in registry.list_uploaders():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="마켓플레이스를 찾을 수 없습니다"
            )

        # 계정 데이터
        account = {
            "marketplace": marketplace_name,
            "name": account_data.get("name"),
            "credentials": account_data.get("credentials", {}),
            "config": account_data.get("config", {}),
            "is_active": True,
            "created_by": user["id"],
            "created_at": datetime.utcnow().isoformat(),
        }

        # DB 저장
        created = await storage.create("marketplace_accounts", account)

        logger.info(f"마켓플레이스 계정 생성: {marketplace_name} - {account['name']}")
        return created

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"계정 생성 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="계정을 생성할 수 없습니다"
        )


@router.put("/{marketplace_name}/config")
async def update_marketplace_config(
    marketplace_name: str,
    config: Dict[str, Any],
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user),
):
    """마켓플레이스 설정 업데이트"""
    try:
        # 레지스트리 확인
        registry = UploaderRegistry()
        if marketplace_name not in registry.list_uploaders():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="마켓플레이스를 찾을 수 없습니다"
            )

        # 설정 업데이트
        mp_data = {
            "name": marketplace_name,
            "config": config,
            "updated_by": user["id"],
            "updated_at": datetime.utcnow().isoformat(),
        }

        # DB 업데이트 또는 생성
        existing = await storage.list("marketplaces", filters={"name": marketplace_name}, limit=1)

        if existing:
            updated = await storage.update("marketplaces", existing[0]["id"], mp_data)
        else:
            updated = await storage.create("marketplaces", mp_data)

        logger.info(f"마켓플레이스 설정 업데이트: {marketplace_name}")
        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"마켓플레이스 설정 업데이트 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="설정을 업데이트할 수 없습니다",
        )


@router.get("/upload/jobs")
async def list_upload_jobs(
    marketplace: Optional[str] = Query(None, description="마켓플레이스 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    limit: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """업로드 작업 목록 조회"""
    try:
        # 필터 조건
        filters = {}
        if marketplace:
            filters["marketplace"] = marketplace
        if status:
            filters["status"] = status

        # 작업 목록 조회
        jobs = await storage.list(
            "upload_jobs", filters=filters, limit=limit, order_by=["-started_at"]
        )

        return {"jobs": jobs}

    except Exception as e:
        logger.error(f"업로드 작업 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="작업 목록을 조회할 수 없습니다",
        )
