"""
우체국택배 배송 추적 시스템
우체국택배 API를 통한 실시간 배송 추적
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType, DeliveryStatus
from dropshipping.storage.base import BaseStorage


class PostTracker(BaseDeliveryTracker):
    """우체국택배 배송 추적"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 우체국 API 설정
        """
        super().__init__(CarrierType.POST, storage, config)

        # API 설정
        self.api_url = "https://service.epost.go.kr/trace.RetrieveDomRigiTraceList.comm"

        # HTTP 클라이언트
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )

        # 상태 매핑
        self.status_mapping = {
            "접수": DeliveryStatus.PENDING,
            "발송": DeliveryStatus.PICKUP,
            "도착": DeliveryStatus.IN_TRANSIT,
            "배달준비": DeliveryStatus.OUT_FOR_DELIVERY,
            "배달완료": DeliveryStatus.DELIVERED,
            "미배달": DeliveryStatus.FAILED,
            "반송": DeliveryStatus.RETURNED,
        }

    async def track(self, tracking_number: str) -> Optional[Dict[str, Any]]:
        """우체국택배 배송 추적"""

        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)

            # API 호출
            response = await self.client.post(
                self.api_url, data={"sid1": tracking_number, "displayHeader": "N"}
            )
            response.raise_for_status()

            # HTML 응답 파싱
            html = response.text
            tracking_info = self._parse_tracking_html(html, tracking_number)

            if tracking_info:
                logger.info(f"우체국택배 추적 성공: {tracking_number}")
                return tracking_info

            logger.warning(f"우체국택배 추적 실패: {tracking_number}")
            return None

        except Exception as e:
            logger.error(f"우체국택배 추적 오류: {str(e)}")
            return None

    async def get_tracking_history(self, tracking_number: str) -> List[Dict[str, Any]]:
        """배송 이력 조회"""

        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)

            # API 호출
            response = await self.client.post(
                self.api_url, data={"sid1": tracking_number, "displayHeader": "N"}
            )
            response.raise_for_status()

            # HTML 응답 파싱
            html = response.text
            history = self._parse_tracking_history(html)

            return history

        except Exception as e:
            logger.error(f"배송 이력 조회 오류: {str(e)}")
            return []

    def _parse_tracking_html(self, html: str, tracking_number: str) -> Optional[Dict[str, Any]]:
        """HTML에서 배송 정보 추출"""

        try:
            # 배송 정보가 없는 경우 체크
            if "배송정보가 없습니다" in html:
                return None

            # 현재 상태 추출 (마지막 row의 상태)
            rows = re.findall(r'<tr.*?class="ma_ltb_list".*?>(.*?)</tr>', html, re.DOTALL)

            if not rows:
                return None

            # 마지막 상태 정보
            last_row = rows[-1]
            cols = re.findall(r"<td.*?>(.*?)</td>", last_row, re.DOTALL)

            if len(cols) < 4:
                return None

            # HTML 태그 제거
            def clean_html(text):
                return re.sub(r"<.*?>", "", text).strip()

            # 상태 정보 추출
            status_text = clean_html(cols[3])
            status = self._map_status(status_text)

            # 위치 정보
            location = clean_html(cols[2])

            # 시간 정보
            date_time = f"{clean_html(cols[0])} {clean_html(cols[1])}"
            timestamp = self.parse_datetime(date_time)

            # 배송완료 시간
            delivered_at = None
            if status == DeliveryStatus.DELIVERED and timestamp:
                delivered_at = timestamp

            return {
                "tracking_number": tracking_number,
                "carrier": self.carrier.value,
                "status": status.value,
                "location": location,
                "message": status_text,
                "delivered_at": delivered_at,
                "updated_at": datetime.now(),
            }

        except Exception as e:
            logger.error(f"HTML 파싱 오류: {str(e)}")
            return None

    def _parse_tracking_history(self, html: str) -> List[Dict[str, Any]]:
        """HTML에서 배송 이력 추출"""

        history = []

        try:
            # 배송 이력 테이블의 모든 행 추출
            rows = re.findall(r'<tr.*?class="ma_ltb_list".*?>(.*?)</tr>', html, re.DOTALL)

            for row in rows:
                # 컬럼 추출
                cols = re.findall(r"<td.*?>(.*?)</td>", row, re.DOTALL)

                if len(cols) >= 4:
                    # HTML 태그 제거
                    def clean_html(text):
                        return re.sub(r"<.*?>", "", text).strip()

                    # 정보 추출
                    date = clean_html(cols[0])
                    time = clean_html(cols[1])
                    location = clean_html(cols[2])
                    status_text = clean_html(cols[3])

                    # 날짜/시간 파싱
                    timestamp = self.parse_datetime(f"{date} {time}")

                    if timestamp:
                        status = self._map_status(status_text)

                        history.append(
                            {
                                "timestamp": timestamp,
                                "location": location,
                                "status": status.value,
                                "details": status_text,
                            }
                        )

            # 시간순 정렬
            history.sort(key=lambda x: x["timestamp"])

        except Exception as e:
            logger.error(f"이력 파싱 오류: {str(e)}")

        return history

    def _map_status(self, status_text: str) -> DeliveryStatus:
        """상태 텍스트를 DeliveryStatus로 매핑"""

        # 정확한 매칭
        if status_text in self.status_mapping:
            return self.status_mapping[status_text]

        # 부분 매칭
        for key, status in self.status_mapping.items():
            if key in status_text:
                return status

        # 키워드 기반 매칭
        if "배달완료" in status_text:
            return DeliveryStatus.DELIVERED
        elif "배달준비" in status_text or "배달출발" in status_text:
            return DeliveryStatus.OUT_FOR_DELIVERY
        elif "도착" in status_text:
            return DeliveryStatus.IN_TRANSIT
        elif "발송" in status_text:
            return DeliveryStatus.PICKUP
        elif "접수" in status_text:
            return DeliveryStatus.PENDING
        elif "반송" in status_text:
            return DeliveryStatus.RETURNED
        elif "미배달" in status_text:
            return DeliveryStatus.FAILED

        # 기본값
        return DeliveryStatus.IN_TRANSIT

    def parse_datetime(self, date_str: str) -> Optional[datetime]:
        """우체국 날짜 형식 파싱"""
        try:
            # 우체국 형식: "2024.01.15 14:30"
            # 또는 "01.15 14:30" (연도 없음)

            # 연도가 없는 경우 현재 연도 추가
            if not re.match(r"\d{4}", date_str):
                current_year = datetime.now().year
                date_str = f"{current_year}.{date_str}"

            # 표준 형식으로 변환
            date_str = date_str.replace(".", "-")

            return datetime.strptime(date_str, "%Y-%m-%d %H:%M")

        except Exception as e:
            logger.debug(f"날짜 파싱 오류: {date_str} - {str(e)}")
            return None

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
