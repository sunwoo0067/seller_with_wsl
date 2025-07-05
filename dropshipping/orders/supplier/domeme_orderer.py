"""
도매매(Domeme) 주문 전달 시스템
도매매 API를 통한 자동 주문 처리
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET
import httpx

from loguru import logger

from dropshipping.models.order import Order, OrderItem
from dropshipping.orders.supplier.base import BaseSupplierOrderer, SupplierType, SupplierOrderStatus
from dropshipping.storage.base import BaseStorage


class DomemeOrderer(BaseSupplierOrderer):
    """도매매 주문 전달자"""
    
    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 도매매 API 설정
        """
        super().__init__(SupplierType.DOMEME, storage, config)
        
        # API 설정
        self.base_url = "https://domemeapi.com/api"
        self.company_code = self.config.get("company_code", "")
        
        # HTTP 클라이언트
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # 배송 방법 코드
        self.delivery_method = self.config.get("delivery_method", "01")  # 01: 택배
        
        # 상태 매핑
        self.status_mapping = {
            "01": SupplierOrderStatus.ORDERED,
            "02": SupplierOrderStatus.CONFIRMED,
            "03": SupplierOrderStatus.PREPARING,
            "04": SupplierOrderStatus.SHIPPED,
            "05": SupplierOrderStatus.DELIVERED,
            "99": SupplierOrderStatus.CANCELLED
        }
    
    async def place_order(
        self,
        order: Order,
        items: List[OrderItem]
    ) -> Tuple[bool, Dict[str, Any]]:
        """도매매에 주문 전달"""
        
        try:
            # XML 요청 생성
            xml_data = self._build_order_xml(order, items)
            
            # API 요청
            url = f"{self.base_url}/order/register"
            headers = {
                "Content-Type": "application/xml; charset=utf-8",
                "X-API-KEY": self.api_key,
                "X-API-SECRET": self.api_secret
            }
            
            response = await self.client.post(
                url,
                content=xml_data,
                headers=headers
            )
            response.raise_for_status()
            
            # 응답 파싱
            result = self._parse_order_response(response.text)
            
            if result["success"]:
                logger.info(f"도매매 주문 성공: {result['order_id']}")
                return True, result
            else:
                logger.error(f"도매매 주문 실패: {result.get('error')}")
                return False, result
                
        except Exception as e:
            logger.error(f"도매매 주문 오류: {str(e)}")
            return False, {"error": str(e)}
    
    async def check_order_status(
        self,
        supplier_order_id: str
    ) -> Dict[str, Any]:
        """도매매 주문 상태 확인"""
        
        try:
            # XML 요청 생성
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <order>
                <companyCode>{self.company_code}</companyCode>
                <orderNo>{supplier_order_id}</orderNo>
            </order>"""
            
            # API 요청
            url = f"{self.base_url}/order/status"
            headers = {
                "Content-Type": "application/xml; charset=utf-8",
                "X-API-KEY": self.api_key,
                "X-API-SECRET": self.api_secret
            }
            
            response = await self.client.post(
                url,
                content=xml_data,
                headers=headers
            )
            response.raise_for_status()
            
            # 응답 파싱
            return self._parse_status_response(response.text)
            
        except Exception as e:
            logger.error(f"상태 조회 오류: {str(e)}")
            return {}
    
    async def cancel_order(
        self,
        supplier_order_id: str,
        reason: str
    ) -> bool:
        """도매매 주문 취소"""
        
        try:
            # XML 요청 생성
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <cancel>
                <companyCode>{self.company_code}</companyCode>
                <orderNo>{supplier_order_id}</orderNo>
                <cancelReason>{reason}</cancelReason>
            </cancel>"""
            
            # API 요청
            url = f"{self.base_url}/order/cancel"
            headers = {
                "Content-Type": "application/xml; charset=utf-8",
                "X-API-KEY": self.api_key,
                "X-API-SECRET": self.api_secret
            }
            
            response = await self.client.post(
                url,
                content=xml_data,
                headers=headers
            )
            response.raise_for_status()
            
            # 응답 확인
            root = ET.fromstring(response.text)
            code = root.find("code").text
            
            return code == "00"
            
        except Exception as e:
            logger.error(f"주문 취소 오류: {str(e)}")
            return False
    
    async def get_tracking_info(
        self,
        supplier_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """배송 정보 조회"""
        
        try:
            # XML 요청 생성
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <tracking>
                <companyCode>{self.company_code}</companyCode>
                <orderNo>{supplier_order_id}</orderNo>
            </tracking>"""
            
            # API 요청
            url = f"{self.base_url}/order/tracking"
            headers = {
                "Content-Type": "application/xml; charset=utf-8",
                "X-API-KEY": self.api_key,
                "X-API-SECRET": self.api_secret
            }
            
            response = await self.client.post(
                url,
                content=xml_data,
                headers=headers
            )
            response.raise_for_status()
            
            # 응답 파싱
            return self._parse_tracking_response(response.text)
            
        except Exception as e:
            logger.error(f"배송 정보 조회 오류: {str(e)}")
            return None
    
    def _build_order_xml(self, order: Order, items: List[OrderItem]) -> str:
        """주문 XML 생성"""
        
        # 주문 금액 계산
        total_amount = sum(item.total_price for item in items)
        
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<order>',
            f'  <companyCode>{self.company_code}</companyCode>',
            f'  <orderDate>{datetime.now().strftime("%Y%m%d")}</orderDate>',
            f'  <orderNo>{order.id}</orderNo>',
            
            # 주문자 정보
            '  <orderer>',
            f'    <name>{order.customer.name}</name>',
            f'    <phone>{order.customer.phone}</phone>',
            f'    <email>{order.customer.email or ""}</email>',
            '  </orderer>',
            
            # 수령자 정보
            '  <receiver>',
            f'    <name>{order.customer.recipient_name}</name>',
            f'    <phone>{order.customer.recipient_phone}</phone>',
            f'    <zipCode>{order.customer.postal_code}</zipCode>',
            f'    <address>{order.customer.address}</address>',
            f'    <addressDetail>{order.customer.address_detail or ""}</addressDetail>',
            f'    <deliveryMessage>{order.customer.delivery_message or ""}</deliveryMessage>',
            '  </receiver>',
            
            # 상품 정보
            '  <items>'
        ]
        
        for item in items:
            # supplier_product_id에서 실제 도매매 상품번호 추출
            # 예: "DM12345" -> "12345"
            product_no = item.supplier_product_id.replace("DM", "")
            
            xml_parts.extend([
                '    <item>',
                f'      <productNo>{product_no}</productNo>',
                f'      <productName>{item.product_name}</productName>',
                f'      <quantity>{item.quantity}</quantity>',
                f'      <price>{int(item.unit_price)}</price>',
            ])
            
            # 옵션 정보가 있으면 추가
            if item.options:
                xml_parts.append('      <options>')
                for key, value in item.options.items():
                    xml_parts.append(f'        <option name="{key}">{value}</option>')
                xml_parts.append('      </options>')
            
            xml_parts.append('    </item>')
        
        xml_parts.extend([
            '  </items>',
            
            # 결제 정보
            '  <payment>',
            f'    <totalAmount>{int(total_amount)}</totalAmount>',
            f'    <deliveryFee>{int(order.payment.shipping_fee)}</deliveryFee>',
            f'    <paymentMethod>{order.payment.method}</paymentMethod>',
            '  </payment>',
            
            # 배송 정보
            '  <delivery>',
            f'    <method>{self.delivery_method}</method>',
            '  </delivery>',
            
            '</order>'
        ])
        
        return '\n'.join(xml_parts)
    
    def _parse_order_response(self, xml_str: str) -> Dict[str, Any]:
        """주문 응답 파싱"""
        try:
            root = ET.fromstring(xml_str)
            code = root.find("code").text
            message = root.find("message").text
            
            if code == "00":  # 성공
                order_no = root.find("orderNo").text
                return {
                    "success": True,
                    "order_id": order_no,
                    "message": message
                }
            else:
                return {
                    "success": False,
                    "error": message,
                    "code": code
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"응답 파싱 오류: {str(e)}"
            }
    
    def _parse_status_response(self, xml_str: str) -> Dict[str, Any]:
        """상태 응답 파싱"""
        try:
            root = ET.fromstring(xml_str)
            code = root.find("code").text
            
            if code == "00":  # 성공
                status_code = root.find("orderStatus").text
                status = self.status_mapping.get(status_code, SupplierOrderStatus.PENDING)
                
                result = {
                    "status": status.value,
                    "status_code": status_code,
                    "status_name": root.find("orderStatusName").text
                }
                
                # 배송 정보가 있으면 추가
                tracking = root.find("tracking")
                if tracking is not None:
                    carrier = tracking.find("carrier")
                    tracking_no = tracking.find("trackingNo")
                    
                    if carrier is not None and tracking_no is not None:
                        result["carrier"] = carrier.text
                        result["tracking_number"] = tracking_no.text
                
                return result
            else:
                return {}
                
        except Exception as e:
            logger.error(f"상태 응답 파싱 오류: {str(e)}")
            return {}
    
    def _parse_tracking_response(self, xml_str: str) -> Optional[Dict[str, Any]]:
        """배송 정보 응답 파싱"""
        try:
            root = ET.fromstring(xml_str)
            code = root.find("code").text
            
            if code == "00":  # 성공
                tracking = root.find("tracking")
                if tracking is not None:
                    return {
                        "carrier": tracking.find("carrier").text,
                        "tracking_number": tracking.find("trackingNo").text,
                        "shipped_at": tracking.find("shippedAt").text,
                        "tracking_url": tracking.find("trackingUrl").text
                    }
            
            return None
                
        except Exception as e:
            logger.error(f"배송 정보 파싱 오류: {str(e)}")
            return None
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()