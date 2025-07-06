"""
주문 관리 기본 클래스
모든 마켓플레이스 주문 관리자의 추상 기반 클래스
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from dropshipping.models.order import Order, OrderStatus
from dropshipping.storage.base import BaseStorage


class OrderManagerType(Enum):
    """주문 관리자 타입"""

    COUPANG = "coupang"
    ELEVENST = "11st"
    NAVER = "naver"
    GMARKET = "gmarket"
    AUCTION = "auction"


class BaseOrderManager(ABC):
    """주문 관리 기본 클래스"""

    def __init__(
        self,
        marketplace: OrderManagerType,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        초기화

        Args:
            marketplace: 마켓플레이스 타입
            storage: 저장소 인스턴스
            config: 주문 관리 설정
        """
        self.marketplace = marketplace
        self.storage = storage
        self.config = config or {}

        # API 설정
        self.api_key = self.config.get("api_key")
        self.api_secret = self.config.get("api_secret")
        self.seller_id = self.config.get("seller_id")

        # 수집 설정
        self.fetch_interval = self.config.get("fetch_interval", 300)  # 5분
        self.batch_size = self.config.get("batch_size", 50)
        self.max_retries = self.config.get("max_retries", 3)

        # 통계
        self.stats = {"fetched": 0, "processed": 0, "failed": 0, "errors": []}

    @abstractmethod
    async def fetch_orders(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Dict[str, Any]]:
        """
        주문 목록 조회

        Args:
            start_date: 조회 시작일
            end_date: 조회 종료일 (None이면 현재)
            status: 주문 상태 필터

        Returns:
            원본 주문 데이터 목록
        """
        pass

    @abstractmethod
    async def fetch_order_detail(self, marketplace_order_id: str) -> Dict[str, Any]:
        """
        주문 상세 조회

        Args:
            marketplace_order_id: 마켓플레이스 주문번호

        Returns:
            원본 주문 상세 데이터
        """
        pass

    @abstractmethod
    async def transform_order(self, raw_order: Dict[str, Any]) -> Order:
        """
        주문 데이터 변환

        Args:
            raw_order: 원본 주문 데이터

        Returns:
            표준 주문 객체
        """
        pass

    @abstractmethod
    async def update_order_status(self, marketplace_order_id: str, status: OrderStatus) -> bool:
        """
        주문 상태 업데이트

        Args:
            marketplace_order_id: 마켓플레이스 주문번호
            status: 새로운 상태

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    async def update_tracking_info(
        self, marketplace_order_id: str, carrier: str, tracking_number: str
    ) -> bool:
        """
        배송 정보 업데이트

        Args:
            marketplace_order_id: 마켓플레이스 주문번호
            carrier: 택배사
            tracking_number: 운송장번호

        Returns:
            성공 여부
        """
        pass

    async def collect_orders(
        self, start_date: Optional[datetime] = None, hours_back: int = 24
    ) -> int:
        """
        주문 수집 (process_new_orders의 간단한 래퍼)

        Args:
            start_date: 시작일 (None이면 hours_back 사용)
            hours_back: 조회할 과거 시간

        Returns:
            수집된 주문 수
        """
        orders = await self.process_new_orders(start_date, hours_back)
        return len(orders)

    async def process_new_orders(
        self, start_date: Optional[datetime] = None, hours_back: int = 24
    ) -> List[Order]:
        """
        신규 주문 처리

        Args:
            start_date: 시작일 (None이면 hours_back 사용)
            hours_back: 조회할 과거 시간

        Returns:
            처리된 주문 목록
        """
        if not start_date:
            start_date = datetime.now() - timedelta(hours=hours_back)

        logger.info(
            f"{self.marketplace.value} 신규 주문 조회 시작 "
            f"(from {start_date.strftime('%Y-%m-%d %H:%M')})"
        )

        try:
            # 1. 주문 목록 조회
            raw_orders = await self.fetch_orders(start_date)
            self.stats["fetched"] += len(raw_orders)

            # 2. 주문 변환 및 저장
            processed_orders = []
            for raw_order in raw_orders:
                try:
                    # 중복 체크
                    marketplace_order_id = self._extract_order_id(raw_order)
                    existing = await self.storage.get(
                        "orders",
                        filters={
                            "marketplace": self.marketplace.value,
                            "marketplace_order_id": marketplace_order_id,
                        },
                    )

                    if existing:
                        logger.debug(f"이미 처리된 주문: {marketplace_order_id}")
                        continue

                    # 주문 변환
                    order = await self.transform_order(raw_order)

                    # 저장
                    await self.storage.create("orders", order.to_dict())
                    processed_orders.append(order)
                    self.stats["processed"] += 1

                    logger.info(f"주문 처리 완료: {order.id}")

                except Exception as e:
                    logger.error(f"주문 처리 오류: {str(e)}")
                    self.stats["failed"] += 1
                    self.stats["errors"].append(
                        {
                            "order_id": self._extract_order_id(raw_order),
                            "error": str(e),
                            "timestamp": datetime.now(),
                        }
                    )

            logger.info(f"주문 처리 완료: " f"조회 {len(raw_orders)}, 처리 {len(processed_orders)}")

            return processed_orders

        except Exception as e:
            logger.error(f"주문 조회 오류: {str(e)}")
            raise

    async def sync_order_status(self, order_ids: Optional[List[str]] = None) -> int:
        """
        주문 상태 동기화

        Args:
            order_ids: 동기화할 주문 ID 목록 (None이면 진행중인 모든 주문)

        Returns:
            업데이트된 주문 수
        """
        # 동기화 대상 주문 조회
        filters = {
            "marketplace": self.marketplace.value,
            "status": {
                "$nin": [
                    OrderStatus.DELIVERED.value,
                    OrderStatus.CANCELLED.value,
                    OrderStatus.REFUNDED.value,
                ]
            },
        }

        if order_ids:
            filters["id"] = {"$in": order_ids}

        orders = await self.storage.list("orders", filters=filters)

        updated_count = 0
        for order_data in orders:
            try:
                # 최신 정보 조회
                raw_order = await self.fetch_order_detail(order_data["marketplace_order_id"])

                # 상태 비교 및 업데이트
                latest_order = await self.transform_order(raw_order)

                updates = {}
                # order_data["status"]는 이미 문자열이므로 .value 비교
                if latest_order.status.value != order_data["status"]:
                    updates["status"] = latest_order.status.value

                # delivery status도 마찬가지로 문자열 비교
                if latest_order.delivery and latest_order.delivery.status.value != order_data["delivery"]["status"]:
                    updates["delivery.status"] = latest_order.delivery.status.value

                if latest_order.delivery and latest_order.delivery.tracking_number != order_data["delivery"].get(
                    "tracking_number"
                ):
                    updates["delivery.tracking_number"] = latest_order.delivery.tracking_number
                    updates["delivery.carrier"] = latest_order.delivery.carrier

                if updates:
                    updates["updated_at"] = datetime.now()
                    await self.storage.update("orders", order_data["id"], updates)
                    updated_count += 1
                    logger.info(f"주문 상태 업데이트: {order_data['id']} - {updates}")

            except Exception as e:
                logger.error(f"주문 상태 동기화 오류 ({order_data['id']}): {e}", exc_info=True)

        return updated_count

    async def cancel_order(
        self, order_id: str, reason: str, detailed_reason: Optional[str] = None
    ) -> bool:
        """
        주문 취소

        Args:
            order_id: 주문 ID
            reason: 취소 사유
            detailed_reason: 상세 사유

        Returns:
            성공 여부
        """
        try:
            # 주문 조회
            order_data = await self.storage.get("orders", order_id)
            if not order_data:
                raise ValueError(f"주문을 찾을 수 없습니다: {order_id}")

            # 취소 가능 여부 확인
            order = Order(**order_data)
            if not order.is_cancellable:
                raise ValueError(f"취소할 수 없는 주문 상태입니다: {order.status}")

            # 마켓플레이스 API로 취소 요청
            success = await self.update_order_status(
                order.marketplace_order_id, OrderStatus.CANCELLED
            )

            if success:
                # DB 업데이트
                updates = {
                    "status": OrderStatus.CANCELLED.value,
                    "updated_at": datetime.now(),
                    "cancel_reason": reason,
                    "cancel_detailed_reason": detailed_reason,
                }
                await self.storage.update("orders", order_id, updates)

                logger.info(f"주문 취소 완료: {order_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"주문 취소 오류: {str(e)}")
            return False

    def _extract_order_id(self, raw_order: Dict[str, Any]) -> str:
        """원본 데이터에서 주문 ID 추출"""
        # 각 마켓플레이스별로 구현 필요
        return raw_order.get("order_id", raw_order.get("orderId", ""))

    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        return {
            **self.stats,
            "marketplace": self.marketplace.value,
            "success_rate": (
                self.stats["processed"] / self.stats["fetched"] if self.stats["fetched"] > 0 else 0
            ),
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {"fetched": 0, "processed": 0, "failed": 0, "errors": []}

    async def _api_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """API 요청 (재시도 포함)"""
        max_retries = self.max_retries
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                # 구체적인 구현은 각 마켓플레이스에서
                raise NotImplementedError
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"API 요청 실패 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(retry_delay)
