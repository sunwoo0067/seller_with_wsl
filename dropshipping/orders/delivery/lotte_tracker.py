"""
롯데글로벌로지스 배송 추적 시스템
롯데글로벌로지스 API를 통한 실시간 배송 추적
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
import json

from loguru import logger

from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType, DeliveryStatus
from dropshipping.storage.base import BaseStorage


class LotteTracker(BaseDeliveryTracker):
    """롯데글로벌로지스 배송 추적"""
    
    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 롯데 API 설정
        """
        super().__init__(CarrierType.LOTTE, storage, config)
        
        # API 설정
        self.api_url = "https://www.lotteglogis.com/home/reservation/tracking/linkView"
        
        # HTTP 클라이언트
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        
        # 상태 매핑
        self.status_mapping = {
            "10": DeliveryStatus.PENDING,      # 접수대기
            "20": DeliveryStatus.PICKUP,       # 접수완료
            "30": DeliveryStatus.PICKUP,       # 집하완료
            "40": DeliveryStatus.IN_TRANSIT,   # 간선상차
            "50": DeliveryStatus.IN_TRANSIT,   # 간선하차
            "55": DeliveryStatus.IN_TRANSIT,   # 지점상차
            "60": DeliveryStatus.IN_TRANSIT,   # 지점도착
            "65": DeliveryStatus.OUT_FOR_DELIVERY,  # 배송출발
            "70": DeliveryStatus.DELIVERED,    # 배송완료
            "80": DeliveryStatus.FAILED,       # 미배달
            "90": DeliveryStatus.RETURNED      # 반송
        }
    
    async def track(self, tracking_number: str) -> Optional[Dict[str, Any]]:
        """롯데글로벌로지스 배송 추적"""
        
        try:
            # 운송장 번호 정규화
            tracking_number = self.normalize_tracking_number(tracking_number)
            
            # API 호출
            response = await self.client.get(
                self.api_url,
                params={"InvNo": tracking_number}
            )
            response.raise_for_status()
            
            # 응답 처리 (HTML 또는 JSON)
            if "application/json" in response.headers.get("content-type", ""):
                data = response.json()
                tracking_info = self._parse_json_response(data, tracking_number)
            else:
                # HTML 응답 처리
                tracking_info = self._parse_html_response(
                    response.text,
                    tracking_number
                )
            
            if tracking_info:
                logger.info(f"롯데글로벌로지스 추적 성공: {tracking_number}")
                return tracking_info
            
            logger.warning(f"롯데글로벌로지스 추적 실패: {tracking_number}")
            return None
                
        except Exception as e:
            logger.error(f"롯데글로벌로지스 추적 오류: {str(e)}")
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
                self.api_url,
                params={"InvNo": tracking_number}
            )
            response.raise_for_status()
            
            # 응답 처리
            if "application/json" in response.headers.get("content-type", ""):
                data = response.json()
                history = self._parse_json_history(data)
            else:
                history = self._parse_html_history(response.text)
            
            return history
            
        except Exception as e:
            logger.error(f"배송 이력 조회 오류: {str(e)}")
            return []
    
    def _parse_json_response(
        self,
        data: Dict[str, Any],
        tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """JSON 응답에서 배송 정보 추출"""
        
        try:
            # 배송 정보
            parcel_info = data.get("parcelResultMap", {})
            
            # 현재 상태
            status_code = parcel_info.get("statusCode", "")
            status = self.status_mapping.get(
                status_code,
                DeliveryStatus.IN_TRANSIT
            )
            
            # 위치 정보
            location = parcel_info.get("branchName", "")
            
            # 상태 메시지
            message = parcel_info.get("statusName", "")
            
            # 배송완료 시간
            delivered_at = None
            if status == DeliveryStatus.DELIVERED:
                delivered_date = parcel_info.get("deliveryDate", "")
                delivered_time = parcel_info.get("deliveryTime", "")
                if delivered_date and delivered_time:
                    delivered_at = self.parse_datetime(
                        f"{delivered_date} {delivered_time}"
                    )
            
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
            logger.error(f"JSON 파싱 오류: {str(e)}")
            return None
    
    def _parse_html_response(
        self,
        html: str,
        tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """HTML 응답에서 배송 정보 추출 (간단 구현)"""
        
        # 실제로는 BeautifulSoup 사용 권장
        # 여기서는 기본 구조만 제공
        
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier.value,
            "status": DeliveryStatus.IN_TRANSIT.value,
            "location": "",
            "message": "배송중",
            "updated_at": datetime.now()
        }
    
    def _parse_json_history(
        self,
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """JSON 응답에서 배송 이력 추출"""
        
        history = []
        
        try:
            # 배송 이력
            tracking_list = data.get("parcelDetailResultMap", {}).get(
                "trackingDetailList",
                []
            )
            
            for detail in tracking_list:
                # 시간 정보
                date = detail.get("regDate", "")
                time = detail.get("regTime", "")
                timestamp = self.parse_datetime(f"{date} {time}")
                
                if timestamp:
                    # 상태 정보
                    status_code = detail.get("statusCode", "")
                    status = self.status_mapping.get(
                        status_code,
                        DeliveryStatus.IN_TRANSIT
                    )
                    
                    history.append({
                        "timestamp": timestamp,
                        "location": detail.get("branchName", ""),
                        "status": status.value,
                        "details": detail.get("statusName", "")
                    })
            
            # 시간순 정렬
            history.sort(key=lambda x: x["timestamp"])
            
        except Exception as e:
            logger.error(f"이력 파싱 오류: {str(e)}")
        
        return history
    
    def _parse_html_history(self, html: str) -> List[Dict[str, Any]]:
        """HTML 응답에서 배송 이력 추출 (간단 구현)"""
        return []
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()