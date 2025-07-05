"""
배송 추적 기본 클래스
모든 택배사 추적 시스템의 추상 기반 클래스
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from dropshipping.storage.base import BaseStorage


class CarrierType(str, Enum):
    """택배사 타입"""

    CJ = "cj"  # CJ대한통운
    HANJIN = "hanjin"  # 한진택배
    LOTTE = "lotte"  # 롯데글로벌로지스
    POST = "post"  # 우체국택배
    LOGEN = "logen"  # 로젠택배
    KGB = "kgb"  # KG로지스
    EPOST = "epost"  # EMS
    FEDEX = "fedex"  # FedEx
    UPS = "ups"  # UPS
    DHL = "dhl"  # DHL


class DeliveryStatus(str, Enum):
    """배송 상태"""

    PENDING = "pending"  # 대기중
    PICKUP = "pickup"  # 집하
    IN_TRANSIT = "in_transit"  # 배송중
    OUT_FOR_DELIVERY = "out_for_delivery"  # 배송출발
    DELIVERED = "delivered"  # 배송완료
    FAILED = "failed"  # 배송실패
    RETURNED = "returned"  # 반송


class BaseDeliveryTracker(ABC):
    """배송 추적 기본 클래스"""

    def __init__(
        self, carrier: CarrierType, storage: BaseStorage, config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화

        Args:
            carrier: 택배사 타입
            storage: 저장소 인스턴스
            config: 택배사 설정
        """
        self.carrier = carrier
        self.storage = storage
        self.config = config or {}

        # API 설정
        self.api_key = self.config.get("api_key")
        self.api_url = self.config.get("api_url")

        # 추적 설정
        self.cache_ttl = self.config.get("cache_ttl", 3600)  # 1시간
        self.update_interval = self.config.get("update_interval", 1800)  # 30분

        # 상태 매핑 (각 택배사별로 오버라이드)
        self.status_mapping: Dict[str, DeliveryStatus] = {}

        # 통계
        self.stats = {"tracked": 0, "delivered": 0, "failed": 0, "errors": []}

    @abstractmethod
    async def track(self, tracking_number: str) -> Optional[Dict[str, Any]]:
        """
        배송 추적

        Args:
            tracking_number: 운송장 번호

        Returns:
            배송 정보 (상태, 위치, 이력 등)
        """
        pass

    @abstractmethod
    async def get_tracking_history(self, tracking_number: str) -> List[Dict[str, Any]]:
        """
        배송 이력 조회

        Args:
            tracking_number: 운송장 번호

        Returns:
            배송 이력 목록
        """
        pass

    async def track_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        주문 배송 추적

        Args:
            order_id: 주문 ID

        Returns:
            배송 정보
        """
        try:
            # 주문 조회
            order = await self.storage.get("orders", order_id)
            if not order:
                logger.error(f"주문을 찾을 수 없습니다: {order_id}")
                return None

            # 배송 정보 확인
            delivery = order.get("delivery", {})
            tracking_number = delivery.get("tracking_number")
            carrier = delivery.get("carrier")

            if not tracking_number:
                logger.debug(f"운송장 번호가 없습니다: {order_id}")
                return None

            # 택배사 확인
            if carrier != self.carrier.value:
                logger.debug(f"다른 택배사입니다: {carrier} (현재: {self.carrier.value})")
                return None

            # 캐시 확인
            cached = await self._get_cached_tracking(order_id, tracking_number)
            if cached:
                return cached

            # 배송 추적
            tracking_info = await self.track(tracking_number)

            if tracking_info:
                # 캐시 저장
                await self._cache_tracking(order_id, tracking_number, tracking_info)

                # 주문 업데이트
                await self._update_order_delivery(order_id, tracking_info)

                self.stats["tracked"] += 1

                # 배송완료 확인
                if tracking_info.get("status") == DeliveryStatus.DELIVERED:
                    self.stats["delivered"] += 1

                return tracking_info
            else:
                self.stats["failed"] += 1
                return None

        except Exception as e:
            logger.error(f"주문 배송 추적 오류 ({order_id}): {str(e)}")
            self.stats["failed"] += 1
            self.stats["errors"].append(
                {"order_id": order_id, "error": str(e), "timestamp": datetime.now()}
            )
            return None

    async def track_batch(self, tracking_numbers: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        배치 배송 추적

        Args:
            tracking_numbers: 운송장 번호 목록

        Returns:
            운송장번호별 배송 정보
        """
        results = {}

        for tracking_number in tracking_numbers:
            try:
                tracking_info = await self.track(tracking_number)
                results[tracking_number] = tracking_info
            except Exception as e:
                logger.error(f"배송 추적 오류 ({tracking_number}): {str(e)}")
                results[tracking_number] = None

        return results

    async def update_all_pending_orders(self) -> Dict[str, Any]:
        """
        모든 배송중 주문 업데이트

        Returns:
            업데이트 결과
        """
        logger.info(f"{self.carrier.value} 배송중 주문 업데이트 시작")

        try:
            # 배송중 주문 조회
            pending_orders = await self.storage.list(
                "orders",
                filters={
                    "delivery.carrier": self.carrier.value,
                    "delivery.status": {
                        "$in": [
                            DeliveryStatus.PICKUP.value,
                            DeliveryStatus.IN_TRANSIT.value,
                            DeliveryStatus.OUT_FOR_DELIVERY.value,
                        ]
                    },
                },
            )

            logger.info(f"업데이트할 주문: {len(pending_orders)}개")

            # 각 주문 추적
            updated = 0
            delivered = 0
            failed = 0

            for order in pending_orders:
                result = await self.track_order(order["id"])

                if result:
                    updated += 1
                    if result.get("status") == DeliveryStatus.DELIVERED:
                        delivered += 1
                else:
                    failed += 1

            return {
                "carrier": self.carrier.value,
                "total": len(pending_orders),
                "updated": updated,
                "delivered": delivered,
                "failed": failed,
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"배송 업데이트 오류: {str(e)}")
            return {"carrier": self.carrier.value, "error": str(e), "timestamp": datetime.now()}

    async def _get_cached_tracking(
        self, order_id: str, tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """캐시된 배송 정보 조회"""
        # 간단한 구현 - 실제로는 Redis 등 사용
        cache_key = f"tracking:{self.carrier.value}:{tracking_number}"

        # DB에서 최근 추적 정보 확인
        order = await self.storage.get("orders", order_id)
        if not order:
            return None

        delivery = order.get("delivery", {})
        last_tracked = delivery.get("last_tracked_at")

        if last_tracked:
            # 캐시 TTL 확인
            last_tracked_dt = datetime.fromisoformat(last_tracked.replace("Z", "+00:00"))
            age = (datetime.now() - last_tracked_dt).total_seconds()

            if age < self.cache_ttl:
                # 캐시 유효
                return {
                    "status": delivery.get("status"),
                    "location": delivery.get("current_location"),
                    "message": delivery.get("status_message"),
                    "estimated_delivery": delivery.get("estimated_delivery"),
                    "cached": True,
                }

        return None

    async def _cache_tracking(
        self, order_id: str, tracking_number: str, tracking_info: Dict[str, Any]
    ):
        """배송 정보 캐시"""
        tracking_info["last_tracked_at"] = datetime.now()

    async def _update_order_delivery(self, order_id: str, tracking_info: Dict[str, Any]):
        """주문 배송 정보 업데이트"""
        updates = {
            "delivery.status": tracking_info.get("status"),
            "delivery.current_location": tracking_info.get("location"),
            "delivery.status_message": tracking_info.get("message"),
            "delivery.last_tracked_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        if tracking_info.get("estimated_delivery"):
            updates["delivery.estimated_delivery"] = tracking_info["estimated_delivery"]

        if tracking_info.get("status") == DeliveryStatus.DELIVERED:
            updates["delivery.delivered_at"] = tracking_info.get("delivered_at", datetime.now())
            updates["status"] = "completed"

        await self.storage.update("orders", order_id, updates)

    def normalize_tracking_number(self, tracking_number: str) -> str:
        """운송장 번호 정규화"""
        # 공백, 하이픈 제거
        return tracking_number.replace(" ", "").replace("-", "")

    def parse_datetime(self, date_str: str) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        # 각 택배사별로 다른 형식 처리
        try:
            # 일반적인 형식들
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y.%m.%d %H:%M:%S",
                "%Y.%m.%d %H:%M",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            return None

        except Exception as e:
            logger.debug(f"날짜 파싱 오류: {date_str} - {str(e)}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        total = self.stats["tracked"] + self.stats["failed"]

        return {
            **self.stats,
            "carrier": self.carrier.value,
            "total": total,
            "success_rate": (self.stats["tracked"] / total if total > 0 else 0),
            "delivery_rate": (
                self.stats["delivered"] / self.stats["tracked"] if self.stats["tracked"] > 0 else 0
            ),
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {"tracked": 0, "delivered": 0, "failed": 0, "errors": []}
