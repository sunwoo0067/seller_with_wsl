"""
네이버 스마트스토어 주문 관리자
Commerce API를 통한 주문 조회 및 관리
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import base64
import httpx

from loguru import logger

from dropshipping.models.order import (
    Order, OrderItem, CustomerInfo, PaymentInfo, DeliveryInfo,
    OrderStatus, PaymentStatus, DeliveryStatus, PaymentMethod
)
from dropshipping.orders.base import BaseOrderManager, OrderManagerType
from dropshipping.storage.base import BaseStorage


class SmartstoreOrderManager(BaseOrderManager):
    """네이버 스마트스토어 주문 관리자"""
    
    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 네이버 API 설정
        """
        super().__init__(OrderManagerType.NAVER, storage, config)
        
        # OAuth 설정
        self.client_id = self.config.get("client_id", "")
        self.client_secret = self.config.get("client_secret", "")
        self.access_token = self.config.get("access_token", "")
        
        # API URL
        self.base_url = "https://api.commerce.naver.com"
        
        # HTTP 클라이언트
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # 주문 상태 매핑
        self.status_mapping = {
            "PAYED": OrderStatus.CONFIRMED,              # 결제완료
            "PLACE_ORDER_RELEASE": OrderStatus.PREPARING, # 발주확인
            "DELIVERING": OrderStatus.SHIPPED,            # 배송중
            "DELIVERED": OrderStatus.DELIVERED,           # 배송완료
            "PURCHASE_DECIDED": OrderStatus.DELIVERED,    # 구매확정
            "EXCHANGED": OrderStatus.EXCHANGED,           # 교환완료
            "CANCELED": OrderStatus.CANCELLED,            # 취소완료
            "RETURNED": OrderStatus.REFUNDED              # 반품완료
        }
        
        # 결제 방법 매핑
        self.payment_method_mapping = {
            "CARD": PaymentMethod.CARD,                      # 신용카드
            "BANK": PaymentMethod.BANK,                      # 계좌이체
            "VIRTUAL_ACCOUNT": PaymentMethod.VIRTUAL_ACCOUNT, # 가상계좌
            "MOBILE": PaymentMethod.PHONE,                   # 휴대폰
            "POINT": PaymentMethod.POINT,                    # 포인트
            "LATER_PAYMENT": PaymentMethod.OTHER             # 후불결제
        }
    
    async def fetch_orders(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        status: Optional[OrderStatus] = None
    ) -> List[Dict[str, Any]]:
        """주문 목록 조회"""
        
        if not end_date:
            end_date = datetime.now()
        
        # API 파라미터
        params = {
            "searchType": "CREATE_DATE",
            "searchStartDate": start_date.strftime("%Y-%m-%d"),
            "searchEndDate": end_date.strftime("%Y-%m-%d"),
            "placeOrderStatus": [],
            "limit": 100
        }
        
        # 상태 필터
        if status:
            naver_status = self._get_naver_status(status)
            if naver_status:
                params["placeOrderStatus"] = [naver_status]
        else:
            # 전체 조회
            params["placeOrderStatus"] = list(self.status_mapping.keys())
        
        orders = []
        next_token = None
        
        while True:
            if next_token:
                params["nextToken"] = next_token
            
            # API 요청
            url = f"{self.base_url}/external/v1/pay-order/seller/product-orders"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            response = await self.client.get(url, params=params, headers=headers)
            
            # 토큰 갱신 필요시
            if response.status_code == 401:
                await self._refresh_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = await self.client.get(url, params=params, headers=headers)
            
            response.raise_for_status()
            data = response.json()
            
            # 주문 추가
            order_list = data.get("data", {}).get("list", [])
            orders.extend(order_list)
            
            # 다음 페이지 확인
            next_token = data.get("data", {}).get("nextToken")
            if not next_token:
                break
        
        logger.info(f"네이버 스마트스토어 주문 {len(orders)}건 조회 완료")
        return orders
    
    async def fetch_order_detail(self, marketplace_order_id: str) -> Dict[str, Any]:
        """주문 상세 조회"""
        
        url = f"{self.base_url}/external/v1/pay-order/seller/product-orders/{marketplace_order_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.get(url, headers=headers)
        
        # 토큰 갱신 필요시
        if response.status_code == 401:
            await self._refresh_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = await self.client.get(url, headers=headers)
        
        response.raise_for_status()
        data = response.json()
        
        return data.get("data", {})
    
    async def transform_order(self, raw_order: Dict[str, Any]) -> Order:
        """주문 데이터 변환"""
        
        # 주문 ID 생성
        order_id = f"NS{raw_order.get('productOrderId', '')}"
        
        # 주문 정보
        order_info = raw_order.get("order", {})
        delivery_info = raw_order.get("delivery", {})
        
        # 주문 항목 생성 (네이버는 주문당 1개 상품)
        options = {}
        if raw_order.get("optionManageCode"):
            # 옵션 정보 파싱
            option_texts = raw_order.get("selectionTexts", [])
            for i, text in enumerate(option_texts):
                options[f"옵션{i+1}"] = text
        
        order_item = OrderItem(
            id=f"{order_id}_ITEM1",
            product_id=raw_order.get("productId", ""),
            marketplace_product_id=raw_order.get("productId", ""),
            supplier_product_id="",  # 네이버는 공급사 코드 미제공
            product_name=raw_order.get("productName", ""),
            variant_id=raw_order.get("optionManageCode"),
            options=options,
            quantity=raw_order.get("quantity", 1),
            unit_price=Decimal(str(raw_order.get("unitPrice", 0))),
            total_price=Decimal(str(raw_order.get("totalPaymentAmount", 0))),
            discount_amount=Decimal(str(raw_order.get("productDiscountAmount", 0))),
            status=self.status_mapping.get(
                raw_order.get("placeOrderStatus"), 
                OrderStatus.PENDING
            )
        )
        
        # 고객 정보
        customer = CustomerInfo(
            name=order_info.get("ordererName", ""),
            phone=self._mask_phone(order_info.get("ordererTel", "")),
            email=None,  # 네이버는 이메일 미제공
            recipient_name=delivery_info.get("receiverName", ""),
            recipient_phone=self._mask_phone(delivery_info.get("receiverTel1", "")),
            postal_code=delivery_info.get("receiverZipCode", ""),
            address=delivery_info.get("receiverAddress1", ""),
            address_detail=delivery_info.get("receiverAddress2"),
            delivery_message=delivery_info.get("deliveryMemo"),
            marketplace_customer_id=order_info.get("ordererId")
        )
        
        # 결제 정보
        payment = PaymentInfo(
            method=self.payment_method_mapping.get(
                order_info.get("paymentMethod", "CARD"),
                PaymentMethod.CARD
            ),
            status=self._get_payment_status(raw_order),
            total_amount=Decimal(str(raw_order.get("totalPaymentAmount", 0))),
            product_amount=Decimal(str(raw_order.get("unitPrice", 0) * raw_order.get("quantity", 1))),
            shipping_fee=Decimal(str(raw_order.get("deliveryFeeAmount", 0))),
            discount_amount=Decimal(str(raw_order.get("productDiscountAmount", 0))),
            transaction_id=order_info.get("paymentId"),
            paid_at=self._parse_datetime(order_info.get("paymentDate"))
        )
        
        # 배송 정보
        delivery = DeliveryInfo(
            status=self._get_delivery_status(raw_order),
            carrier=delivery_info.get("deliveryCompany"),
            tracking_number=delivery_info.get("trackingNumber"),
            shipped_at=self._parse_datetime(delivery_info.get("sendDate")),
            delivered_at=self._parse_datetime(delivery_info.get("deliveredDate")),
            estimated_delivery=None  # 네이버는 예상 배송일 미제공
        )
        
        # 주문 생성
        order = Order(
            id=order_id,
            marketplace=self.marketplace.value,
            marketplace_order_id=raw_order.get("productOrderId", ""),
            order_date=self._parse_datetime(order_info.get("orderDate")),
            status=self.status_mapping.get(
                raw_order.get("placeOrderStatus"),
                OrderStatus.PENDING
            ),
            items=[order_item],
            customer=customer,
            payment=payment,
            delivery=delivery,
            raw_data=raw_order
        )
        
        return order
    
    async def update_order_status(
        self,
        marketplace_order_id: str,
        status: OrderStatus
    ) -> bool:
        """주문 상태 업데이트"""
        
        # 네이버는 발주확인, 발송처리만 API 지원
        if status == OrderStatus.PREPARING:
            return await self._confirm_order(marketplace_order_id)
        elif status == OrderStatus.SHIPPED:
            # 발송처리는 운송장 번호가 필요하므로 update_tracking_info 사용
            logger.warning("발송처리는 update_tracking_info를 사용하세요")
            return False
        else:
            logger.warning(f"지원하지 않는 상태 업데이트: {status}")
            return False
    
    async def update_tracking_info(
        self,
        marketplace_order_id: str,
        carrier: str,
        tracking_number: str
    ) -> bool:
        """배송 정보 업데이트 (발송처리)"""
        
        url = f"{self.base_url}/external/v1/pay-order/seller/product-orders/{marketplace_order_id}/dispatch"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # 택배사 코드 변환
        carrier_code = self._get_carrier_code(carrier)
        
        data = {
            "dispatchProductOrders": [{
                "productOrderId": marketplace_order_id,
                "deliveryMethod": "DELIVERY",
                "deliveryCompany": carrier_code,
                "trackingNumber": tracking_number
            }]
        }
        
        response = await self.client.patch(url, json=data, headers=headers)
        
        # 토큰 갱신 필요시
        if response.status_code == 401:
            await self._refresh_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = await self.client.patch(url, json=data, headers=headers)
        
        return response.status_code == 200
    
    async def _refresh_token(self):
        """OAuth 토큰 갱신"""
        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        
        # Basic 인증 헤더
        credentials = f"{self.client_id}:{self.client_secret}"
        auth_header = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials",
            "type": "SELF"
        }
        
        response = await self.client.post(url, data=data, headers=headers)
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data.get("access_token", "")
        
        logger.info("네이버 OAuth 토큰 갱신 완료")
    
    def _mask_phone(self, phone: str) -> str:
        """전화번호 마스킹 (개인정보보호)"""
        if len(phone) >= 8:
            return phone[:3] + "****" + phone[-4:]
        return phone
    
    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not date_str:
            return None
        
        try:
            # ISO 형식
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # YYYY-MM-DD 형식
            else:
                return datetime.strptime(date_str, "%Y-%m-%d")
        except:
            return None
    
    def _get_payment_status(self, raw_order: Dict[str, Any]) -> PaymentStatus:
        """결제 상태 결정"""
        place_order_status = raw_order.get("placeOrderStatus", "")
        
        if place_order_status in ["PAYED", "PLACE_ORDER_RELEASE", "DELIVERING", "DELIVERED", "PURCHASE_DECIDED"]:
            return PaymentStatus.COMPLETED
        elif place_order_status == "CANCELED":
            return PaymentStatus.CANCELLED
        elif place_order_status == "RETURNED":
            return PaymentStatus.REFUNDED
        else:
            return PaymentStatus.PENDING
    
    def _get_delivery_status(self, raw_order: Dict[str, Any]) -> DeliveryStatus:
        """배송 상태 결정"""
        place_order_status = raw_order.get("placeOrderStatus", "")
        
        if place_order_status == "PLACE_ORDER_RELEASE":
            return DeliveryStatus.PREPARING
        elif place_order_status == "DELIVERING":
            return DeliveryStatus.IN_TRANSIT
        elif place_order_status in ["DELIVERED", "PURCHASE_DECIDED"]:
            return DeliveryStatus.DELIVERED
        else:
            return DeliveryStatus.PENDING
    
    def _get_naver_status(self, status: OrderStatus) -> Optional[str]:
        """OrderStatus를 네이버 상태로 변환"""
        reverse_mapping = {v: k for k, v in self.status_mapping.items()}
        return reverse_mapping.get(status)
    
    def _get_carrier_code(self, carrier_name: str) -> str:
        """택배사 이름을 코드로 변환"""
        carrier_codes = {
            "CJ대한통운": "CJGLS",
            "한진택배": "HANJIN",
            "롯데택배": "HDEXP",
            "로젠택배": "LOGEN",
            "우체국택배": "EPOST",
            "대한통운": "CJGLS",
            "경동택배": "KDEXP",
            "CVS편의점택배": "CVSNET",
            "CU편의점택배": "CUPOST",
            "GS편의점택배": "GSPOST"
        }
        return carrier_codes.get(carrier_name, "DIRECT")  # 직접배송
    
    async def _confirm_order(self, marketplace_order_id: str) -> bool:
        """발주 확인"""
        url = f"{self.base_url}/external/v1/pay-order/seller/product-orders/{marketplace_order_id}/confirm"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.patch(url, headers=headers)
        
        # 토큰 갱신 필요시
        if response.status_code == 401:
            await self._refresh_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = await self.client.patch(url, headers=headers)
        
        return response.status_code == 200
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()