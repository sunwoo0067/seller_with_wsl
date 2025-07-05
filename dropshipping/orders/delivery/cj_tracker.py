"""
CJ대한통운 배송 추적 시스템
CJ대한통운 API를 통한 실시간 배송 추적
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
import re

from loguru import logger

from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType, DeliveryStatus
from dropshipping.storage.base import BaseStorage


class CJTracker(BaseDeliveryTracker):
    """CJ대한통운 배송 추적"""
    
    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: CJ대한통운 API 설정
        """
        super().__init__(CarrierType.CJ, storage, config)
        
        # API 설정
        self.api_url = "https://www.cjlogistics.com/ko/tool/parcel/tracking"
        self.mobile_url = "https://m.cjlogistics.com/ko/tool/parcel/tracking-detail"
        
        # HTTP 클라이언트
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        
        # 상태 매핑
        self.status_mapping = {
            "접수": DeliveryStatus.PENDING,
            "집하": DeliveryStatus.PICKUP,
            "간선상차": DeliveryStatus.IN_TRANSIT,
            "간선하차": DeliveryStatus.IN_TRANSIT,
            "배송출발": DeliveryStatus.OUT_FOR_DELIVERY,
            "배송완료": DeliveryStatus.DELIVERED,
            "미배달": DeliveryStatus.FAILED,
            "반송": DeliveryStatus.RETURNED
        }
    
    async def track(self, tracking_number: str) -> Optional[Dict[str, Any]]:
        """CJ대한통운 배송 추적"""
        
        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)
            
            # API 호출
            response = await self.client.get(
                self.mobile_url,
                params={"paramInvcNo": tracking_number}
            )
            response.raise_for_status()
            
            # HTML 파싱 (실제로는 BeautifulSoup 사용 권장)
            html = response.text
            
            # 배송 정보 추출
            tracking_info = self._parse_tracking_html(html, tracking_number)
            
            if tracking_info:
                logger.info(f"CJ대한통운 추적 성공: {tracking_number}")
                return tracking_info
            else:
                logger.warning(f"CJ대한통운 추적 실패: {tracking_number}")
                return None
                
        except Exception as e:
            logger.error(f"CJ대한통운 추적 오류: {str(e)}")
            return None
    
    async def get_tracking_history(
        self,
        tracking_number: str
    ) -> List[Dict[str, Any]]:
        """배송 이력 조회"""
        
        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)
            
            # API 호출
            response = await self.client.get(
                self.mobile_url,
                params={"paramInvcNo": tracking_number}
            )
            response.raise_for_status()
            
            # HTML 파싱
            html = response.text
            
            # 배송 이력 추출
            history = self._parse_tracking_history(html)
            
            return history
            
        except Exception as e:
            logger.error(f"배송 이력 조회 오류: {str(e)}")
            return []
    
    def _parse_tracking_html(
        self,
        html: str,
        tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """HTML에서 배송 정보 추출"""
        
        try:
            # 간단한 정규식 파싱 (실제로는 BeautifulSoup 사용)
            
            # 현재 상태 추출
            status_match = re.search(
                r'class="state_ico.*?>(.*?)</span>',
                html,
                re.DOTALL
            )
            
            if not status_match:
                return None
            
            status_text = status_match.group(1).strip()
            status = self._map_status(status_text)
            
            # 현재 위치 추출
            location_match = re.search(
                r'현재위치.*?<td>(.*?)</td>',
                html,
                re.DOTALL
            )
            
            location = ""
            if location_match:
                location = location_match.group(1).strip()
                location = re.sub(r'<.*?>', '', location)  # HTML 태그 제거
            
            # 배송 메시지
            message_match = re.search(
                r'배송상태.*?<td>(.*?)</td>',
                html,
                re.DOTALL
            )
            
            message = status_text
            if message_match:
                message = message_match.group(1).strip()
                message = re.sub(r'<.*?>', '', message)
            
            # 배송완료 시간
            delivered_at = None
            if status == DeliveryStatus.DELIVERED:
                time_match = re.search(
                    r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})',
                    html
                )
                if time_match:
                    delivered_at = self.parse_datetime(time_match.group(1))
            
            return {
                "tracking_number": tracking_number,
                "carrier": self.carrier.value,
                "status": status.value,
                "location": location,
                "message": message,
                "delivered_at": delivered_at,
                "updated_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"HTML 파싱 오류: {str(e)}")
            return None
    
    def _parse_tracking_history(self, html: str) -> List[Dict[str, Any]]:
        """HTML에서 배송 이력 추출"""
        
        history = []
        
        try:
            # 배송 이력 테이블 찾기
            table_match = re.search(
                r'<table.*?class="tbl_list".*?>(.*?)</table>',
                html,
                re.DOTALL
            )
            
            if not table_match:
                return history
            
            table_html = table_match.group(1)
            
            # 각 행 추출
            rows = re.findall(
                r'<tr.*?>(.*?)</tr>',
                table_html,
                re.DOTALL
            )
            
            for row in rows:
                # 컬럼 추출
                cols = re.findall(
                    r'<td.*?>(.*?)</td>',
                    row,
                    re.DOTALL
                )
                
                if len(cols) >= 4:
                    # HTML 태그 제거
                    date_time = re.sub(r'<.*?>', '', cols[0]).strip()
                    location = re.sub(r'<.*?>', '', cols[1]).strip()
                    status = re.sub(r'<.*?>', '', cols[2]).strip()
                    details = re.sub(r'<.*?>', '', cols[3]).strip()
                    
                    # 날짜 파싱
                    timestamp = self.parse_datetime(date_time)
                    
                    if timestamp:
                        history.append({
                            "timestamp": timestamp,
                            "location": location,
                            "status": self._map_status(status).value,
                            "details": details
                        })
            
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
        if "완료" in status_text:
            return DeliveryStatus.DELIVERED
        elif "출발" in status_text:
            return DeliveryStatus.OUT_FOR_DELIVERY
        elif "상차" in status_text or "하차" in status_text:
            return DeliveryStatus.IN_TRANSIT
        elif "집하" in status_text:
            return DeliveryStatus.PICKUP
        elif "접수" in status_text:
            return DeliveryStatus.PENDING
        elif "반송" in status_text:
            return DeliveryStatus.RETURNED
        elif "미배달" in status_text or "실패" in status_text:
            return DeliveryStatus.FAILED
        
        # 기본값
        return DeliveryStatus.IN_TRANSIT
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()