"""
주문 관련 API 엔드포인트
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dropshipping.api.dependencies import (
    Pagination,
    get_current_user,
    get_storage,
    rate_limiter,
    require_api_key,
)
from dropshipping.models.order import OrderStatus
from dropshipping.monitoring import get_logger
from dropshipping.storage.base import BaseStorage

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
async def list_orders(
    marketplace: Optional[str] = Query(None, description="마켓플레이스 필터"),
    status: Optional[OrderStatus] = Query(None, description="주문 상태 필터"),
    date_from: Optional[date] = Query(None, description="시작일"),
    date_to: Optional[date] = Query(None, description="종료일"),
    search: Optional[str] = Query(None, description="검색어 (주문번호, 구매자명)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """주문 목록 조회"""
    try:
        # 페이지네이션 설정
        pagination = Pagination(page=page, page_size=page_size)

        # 필터 조건 생성
        filters = {}
        if marketplace:
            filters["marketplace"] = marketplace
        if status:
            filters["status"] = status.value
        if date_from:
            filters["created_at__gte"] = date_from.isoformat()
        if date_to:
            filters["created_at__lte"] = date_to.isoformat()
        if search:
            filters["order_number__icontains"] = search

        # 데이터 조회
        orders = await storage.list(
            "orders",
            filters=filters,
            limit=pagination.limit,
            offset=pagination.offset,
            order_by=["-created_at"],
        )

        # 전체 개수 조회
        total = await storage.count("orders", filters=filters)

        # 응답 생성
        return pagination.paginate(total, orders)

    except Exception as e:
        logger.error(f"주문 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="주문 목록을 조회할 수 없습니다",
        )


@router.get("/{order_id}")
async def get_order(
    order_id: str, storage: BaseStorage = Depends(get_storage), _: None = Depends(rate_limiter)
):
    """주문 상세 조회"""
    try:
        order = await storage.get("orders", order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="주문을 찾을 수 없습니다"
            )

        # 주문 상품 조회
        order_items = await storage.list("order_items", filters={"order_id": order_id})

        order["items"] = order_items
        return order

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"주문 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="주문을 조회할 수 없습니다"
        )


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: OrderStatus,
    tracking_number: Optional[str] = None,
    tracking_company: Optional[str] = None,
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user),
):
    """주문 상태 업데이트"""
    try:
        # 기존 주문 확인
        order = await storage.get("orders", order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="주문을 찾을 수 없습니다"
            )

        # 상태 업데이트 데이터
        update_data = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": user["id"],
        }

        # 배송 정보 업데이트
        if status == OrderStatus.SHIPPED and tracking_number:
            update_data.update(
                {
                    "tracking_number": tracking_number,
                    "tracking_company": tracking_company,
                    "shipped_at": datetime.utcnow().isoformat(),
                }
            )

        # DB 업데이트
        updated = await storage.update("orders", order_id, update_data)

        # 이력 기록
        await storage.create(
            "order_status_history",
            {
                "order_id": order_id,
                "status": status.value,
                "tracking_number": tracking_number,
                "tracking_company": tracking_company,
                "created_by": user["id"],
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info(f"주문 상태 업데이트: {order_id} -> {status.value}")
        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"주문 상태 업데이트 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="주문 상태를 업데이트할 수 없습니다",
        )


@router.post("/sync")
async def sync_orders(
    marketplace: Optional[str] = Query(None, description="특정 마켓플레이스만 동기화"),
    date_from: Optional[date] = Query(None, description="동기화 시작일"),
    date_to: Optional[date] = Query(None, description="동기화 종료일"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(require_api_key),
):
    """주문 동기화"""
    try:
        # TODO: 실제 동기화 로직 구현
        # 1. 각 마켓플레이스 API에서 주문 조회
        # 2. 신규 주문 DB에 저장
        # 3. 기존 주문 상태 업데이트

        # 임시 응답
        return {
            "status": "synced",
            "synced_at": datetime.utcnow().isoformat(),
            "marketplace": marketplace or "all",
            "new_orders": 0,
            "updated_orders": 0,
        }

    except Exception as e:
        logger.error(f"주문 동기화 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="주문을 동기화할 수 없습니다"
        )


@router.get("/statistics/summary")
async def get_order_statistics(
    date_from: Optional[date] = Query(None, description="시작일"),
    date_to: Optional[date] = Query(None, description="종료일"),
    marketplace: Optional[str] = Query(None, description="마켓플레이스 필터"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """주문 통계 요약"""
    try:
        # 필터 조건
        filters = {}
        if date_from:
            filters["created_at__gte"] = date_from.isoformat()
        if date_to:
            filters["created_at__lte"] = date_to.isoformat()
        if marketplace:
            filters["marketplace"] = marketplace

        # 전체 주문 수
        total_orders = await storage.count("orders", filters=filters)

        # 상태별 주문 수 (임시 구현)
        status_counts = {
            "pending": 0,
            "paid": 0,
            "preparing": 0,
            "shipped": 0,
            "delivered": 0,
            "cancelled": 0,
        }

        # 매출 통계 (임시 구현)
        revenue_stats = {"total_revenue": 0, "average_order_value": 0, "top_products": []}

        return {
            "period": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None,
            },
            "total_orders": total_orders,
            "status_distribution": status_counts,
            "revenue": revenue_stats,
        }

    except Exception as e:
        logger.error(f"주문 통계 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="주문 통계를 조회할 수 없습니다",
        )


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    reason: str = Query(..., description="취소 사유"),
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user),
):
    """주문 취소"""
    try:
        # 기존 주문 확인
        order = await storage.get("orders", order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="주문을 찾을 수 없습니다"
            )

        # 취소 가능 상태 확인
        if order["status"] not in ["pending", "paid", "preparing"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 배송된 주문은 취소할 수 없습니다",
            )

        # 주문 취소 처리
        update_data = {
            "status": OrderStatus.CANCELLED.value,
            "cancel_reason": reason,
            "cancelled_at": datetime.utcnow().isoformat(),
            "cancelled_by": user["id"],
        }

        updated = await storage.update("orders", order_id, update_data)

        # TODO: 마켓플레이스 API로 취소 요청 전송

        logger.info(f"주문 취소: {order_id}")
        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"주문 취소 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="주문을 취소할 수 없습니다"
        )


@router.get("/{order_id}/tracking")
async def get_tracking_info(
    order_id: str, storage: BaseStorage = Depends(get_storage), _: None = Depends(rate_limiter)
):
    """배송 추적 정보 조회"""
    try:
        # 주문 조회
        order = await storage.get("orders", order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="주문을 찾을 수 없습니다"
            )

        # 배송 정보 확인
        if not order.get("tracking_number"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="배송 정보가 없습니다"
            )

        # TODO: 실제 배송 추적 API 연동
        # 임시 응답
        return {
            "order_id": order_id,
            "tracking_number": order.get("tracking_number"),
            "tracking_company": order.get("tracking_company"),
            "status": "in_transit",
            "location": "서울 물류센터",
            "estimated_delivery": "2024-01-15",
            "history": [
                {
                    "timestamp": "2024-01-13 10:00:00",
                    "location": "출발지 물류센터",
                    "status": "집하",
                }
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배송 추적 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="배송 정보를 조회할 수 없습니다",
        )
