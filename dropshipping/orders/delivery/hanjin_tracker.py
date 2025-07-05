"""
한진택배 배송 추적 시스템
한진택배 API를 통한 실시간 배송 추적
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType, DeliveryStatus
from dropshipping.storage.base import BaseStorage


class HanjinTracker(BaseDeliveryTracker):
    """한진택배 배송 추적"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 한진택배 API 설정
        """
        super().__init__(CarrierType.HANJIN, storage, config)

        # API 설정
        self.api_url = "https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillResult.do"

        # HTTP 클라이언트
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.hanjin.com",
            },
        )

        # 상태 매핑
        self.status_mapping = {
            "11": DeliveryStatus.PENDING,  # 접수
            "12": DeliveryStatus.PICKUP,  # 집하
            "31": DeliveryStatus.IN_TRANSIT,  # 간선상차
            "32": DeliveryStatus.IN_TRANSIT,  # 간선하차
            "41": DeliveryStatus.IN_TRANSIT,  # 지점상차
            "42": DeliveryStatus.IN_TRANSIT,  # 지점하차
            "43": DeliveryStatus.OUT_FOR_DELIVERY,  # 배송출발
            "44": DeliveryStatus.DELIVERED,  # 배송완료
            "91": DeliveryStatus.FAILED,  # 미배달
            "99": DeliveryStatus.RETURNED,  # 반송
        }

    async def track(self, tracking_number: str) -> Optional[Dict[str, Any]]:
        """한진택배 배송 추적"""

        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)

            # API 호출
            response = await self.client.post(
                self.api_url, data={"wblnum": tracking_number, "mCode": "MN038"}  # 한진택배 코드
            )
            response.raise_for_status()

            # JSON 응답 파싱
            data = response.json()

            if data.get("result") == "Y":
                # 배송 정보 추출
                tracking_info = self._parse_tracking_data(data, tracking_number)

                if tracking_info:
                    logger.info(f"한진택배 추적 성공: {tracking_number}")
                    return tracking_info

            logger.warning(f"한진택배 추적 실패: {tracking_number}")
            return None

        except Exception as e:
            logger.error(f"한진택배 추적 오류: {str(e)}")
            return None

    async def get_tracking_history(self, tracking_number: str) -> List[Dict[str, Any]]:
        """배송 이력 조회"""

        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)

            # API 호출
            response = await self.client.post(
                self.api_url, data={"wblnum": tracking_number, "mCode": "MN038"}
            )
            response.raise_for_status()

            # JSON 응답 파싱
            data = response.json()

            if data.get("result") == "Y":
                # 배송 이력 추출
                history = self._parse_tracking_history(data)
                return history

            return []

        except Exception as e:
            logger.error(f"배송 이력 조회 오류: {str(e)}")
            return []

    def _parse_tracking_data(
        self, data: Dict[str, Any], tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """JSON 데이터에서 배송 정보 추출"""

        try:
            # 현재 상태 정보
            current_status = data.get("stat", "")
            status_code = data.get("statCode", "")

            # 상태 매핑
            status = self.status_mapping.get(status_code, DeliveryStatus.IN_TRANSIT)

            # 현재 위치
            location = data.get("location", "")

            # 배송 메시지
            message = current_status

            # 배송완료 정보
            delivered_at = None
            if status == DeliveryStatus.DELIVERED:
                delivered_date = data.get("deliveredDate", "")
                delivered_time = data.get("deliveredTime", "")
                if delivered_date and delivered_time:
                    delivered_at = self.parse_datetime(f"{delivered_date} {delivered_time}")

            # 예상 배송일
            estimated_delivery = None
            estimated_date = data.get("estimatedDate", "")
            if estimated_date:
                estimated_delivery = self.parse_datetime(estimated_date)

            return {
                "tracking_number": tracking_number,
                "carrier": self.carrier.value,
                "status": status.value,
                "location": location,
                "message": message,
                "delivered_at": delivered_at,
                "estimated_delivery": estimated_delivery,
                "updated_at": datetime.now(),
            }

        except Exception as e:
            logger.error(f"데이터 파싱 오류: {str(e)}")
            return None

    def _parse_tracking_history(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """JSON 데이터에서 배송 이력 추출"""

        history = []

        try:
            # 배송 이력 리스트
            items = data.get("items", [])

            for item in items:
                # 시간 정보
                date = item.get("date", "")
                time = item.get("time", "")
                timestamp = self.parse_datetime(f"{date} {time}")

                if timestamp:
                    # 상태 정보
                    status_code = item.get("statCode", "")
                    status = self.status_mapping.get(status_code, DeliveryStatus.IN_TRANSIT)

                    history.append(
                        {
                            "timestamp": timestamp,
                            "location": item.get("location", ""),
                            "status": status.value,
                            "details": item.get("stat", ""),
                        }
                    )

            # 시간순 정렬
            history.sort(key=lambda x: x["timestamp"])

        except Exception as e:
            logger.error(f"이력 파싱 오류: {str(e)}")

        return history

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
