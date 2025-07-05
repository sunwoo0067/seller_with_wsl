"""
쿠팡 주문 관리자
쿠팡 WING API를 통한 주문 조회 및 관리
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import time
import httpx

from loguru import logger

from dropshipping.models.order import (
    Order, OrderItem, CustomerInfo, PaymentInfo, DeliveryInfo,
    OrderStatus, PaymentStatus, DeliveryStatus, PaymentMethod
)
from dropshipping.orders.base import BaseOrderManager, OrderManagerType
from dropshipping.storage.base import BaseStorage


class CoupangOrderManager(BaseOrderManager):
    """쿠팡 주문 관리자"""
    
    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 쿠팡 API 설정
        """
        super().__init__(OrderManagerType.COUPANG, storage, config)
        
        # API 설정
        self.vendor_id = self.config.get("vendor_id", "")
        self.test_mode = self.config.get("test_mode", False)
        
        # API URL
        self.base_url = (
            "https://api-gateway-it.coupang.com" if self.test_mode
            else "https://api-gateway.coupang.com"
        )
        
        # HTTP 클라이언트
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # 주문 상태 매핑
        self.status_mapping = {
            "ACCEPT": OrderStatus.CONFIRMED,
            "INSTRUCT": OrderStatus.PREPARING,
            "DEPARTURE": OrderStatus.SHIPPED,
            "DELIVERING": OrderStatus.SHIPPED,
            "FINAL_DELIVERY": OrderStatus.DELIVERED,
            "NONE_TRACKING": OrderStatus.DELIVERED,
            "CANCEL": OrderStatus.CANCELLED
        }
        
        # 결제 상태 매핑
        self.payment_status_mapping = {
            "PAY_SUCCESS": PaymentStatus.COMPLETED,
            "PAY_FAIL": PaymentStatus.FAILED,
            "PAY_CANCEL": PaymentStatus.CANCELLED,
            "REFUND_SUCCESS": PaymentStatus.REFUNDED
        }
        
        # 결제 방법 매핑
        self.payment_method_mapping = {
            "CREDIT_CARD": PaymentMethod.CARD,
            "BANK_TRANSFER": PaymentMethod.BANK,
            "VIRTUAL_ACCOUNT": PaymentMethod.VIRTUAL_ACCOUNT,
            "PHONE": PaymentMethod.PHONE,
            "CASH": PaymentMethod.CASH
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
        
        # 쿠팡 API는 최대 31일 조회 가능
        if (end_date - start_date).days > 31:
            raise ValueError("조회 기간은 31일을 초과할 수 없습니다")
        
        # API 파라미터
        params = {
            "vendorId": self.vendor_id,
            "createdAtFrom": start_date.strftime("%Y-%m-%d"),
            "createdAtTo": end_date.strftime("%Y-%m-%d"),
            "status": "ALL",
            "maxPerPage": 50
        }
        
        # 상태 필터
        if status:
            coupang_status = self._get_coupang_status(status)
            if coupang_status:
                params["status"] = coupang_status
        
        orders = []
        next_token = None
        
        while True:
            if next_token:
                params["nextToken"] = next_token
            
            # API 요청
            path = "/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/ordersheets"
            url = f"{self.base_url}{path.format(vendorId=self.vendor_id)}"
            
            headers = self._create_auth_headers("GET", path, params)
            
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("code") == "SUCCESS":
                order_sheets = data.get("data", [])
                orders.extend(order_sheets)
                
                # 다음 페이지 확인
                next_token = data.get("nextToken")
                if not next_token:
                    break
            else:
                raise Exception(f"주문 조회 실패: {data.get('message')}")
        
        logger.info(f"쿠팡 주문 {len(orders)}건 조회 완료")
        return orders
    
    async def fetch_order_detail(self, marketplace_order_id: str) -> Dict[str, Any]:
        """주문 상세 조회"""
        
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{marketplace_order_id}"
        url = f"{self.base_url}{path}"
        
        headers = self._create_auth_headers("GET", path, {})
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") == "SUCCESS":
            return data.get("data")
        else:
            raise Exception(f"주문 상세 조회 실패: {data.get('message')}")
    
    async def transform_order(self, raw_order: Dict[str, Any]) -> Order:
        """주문 데이터 변환"""
        
        # 주문 ID 생성
        order_id = f"CP{raw_order['orderId']}"
        
        # 주문 항목 변환
        items = []
        for idx, item in enumerate(raw_order.get("orderItems", [])):
            order_item = OrderItem(
                id=f"{order_id}_ITEM{idx+1}",
                product_id=item.get("sellerProductId", ""),
                marketplace_product_id=str(item.get("productId", "")),
                supplier_product_id=item.get("vendorItemId", ""),
                product_name=item.get("sellerProductName", ""),
                variant_id=item.get("vendorItemPackageId"),
                options=self._parse_options(item),
                quantity=item.get("shippingCount", 1),
                unit_price=Decimal(str(item.get("orderPrice", 0))),
                total_price=Decimal(str(item.get("orderPrice", 0) * item.get("shippingCount", 1))),
                discount_amount=Decimal(str(item.get("discountPrice", 0))),
                status=self.status_mapping.get(
                    item.get("status"), 
                    OrderStatus.PENDING
                )
            )
            items.append(order_item)
        
        # 고객 정보
        customer = CustomerInfo(
            name=raw_order.get("ordererName", ""),
            phone=raw_order.get("ordererPhoneNumber", ""),
            email=raw_order.get("ordererEmail"),
            recipient_name=raw_order.get("receiverName", ""),
            recipient_phone=raw_order.get("receiverPhoneNumber1", ""),
            postal_code=raw_order.get("receiverPostCode", ""),
            address=raw_order.get("receiverAddr1", ""),
            address_detail=raw_order.get("receiverAddr2"),
            delivery_message=raw_order.get("parcelPrintMessage"),
            marketplace_customer_id=raw_order.get("customerId")
        )
        
        # 결제 정보
        payment = PaymentInfo(
            method=self.payment_method_mapping.get(
                raw_order.get("paymentMethod", "CREDIT_CARD"),
                PaymentMethod.CARD
            ),
            status=self.payment_status_mapping.get(
                raw_order.get("paymentStatus"),
                PaymentStatus.PENDING
            ),
            total_amount=Decimal(str(raw_order.get("totalPaidAmount", 0))),
            product_amount=Decimal(str(raw_order.get("totalPaidAmount", 0))) - Decimal(str(raw_order.get("shippingPrice", 2500))),
            shipping_fee=Decimal(str(raw_order.get("shippingPrice", 2500))),
            discount_amount=Decimal(str(raw_order.get("discountPrice", 0))),
            transaction_id=raw_order.get("paymentTransactionId"),
            paid_at=self._parse_datetime(raw_order.get("paidAt"))
        )
        
        # 배송 정보
        delivery = DeliveryInfo(
            status=self._get_delivery_status(raw_order),
            carrier=raw_order.get("deliveryCompanyName"),
            tracking_number=raw_order.get("invoiceNumber"),
            shipped_at=self._parse_datetime(raw_order.get("shippedAt")),
            delivered_at=self._parse_datetime(raw_order.get("deliveredAt")),
            estimated_delivery=self._parse_datetime(raw_order.get("estimatedDeliveryDate"))
        )
        
        # 주문 생성
        order = Order(
            id=order_id,
            marketplace=self.marketplace.value,
            marketplace_order_id=str(raw_order["orderId"]),
            order_date=self._parse_datetime(raw_order["orderedAt"]),
            status=self._get_order_status(raw_order),
            items=items,
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
        
        # 쿠팡은 상태별로 다른 API 사용
        if status == OrderStatus.CANCELLED:
            return await self._cancel_order(marketplace_order_id)
        elif status == OrderStatus.PREPARING:
            return await self._confirm_order(marketplace_order_id)
        else:
            logger.warning(f"지원하지 않는 상태 업데이트: {status}")
            return False
    
    async def update_tracking_info(
        self,
        marketplace_order_id: str,
        carrier: str,
        tracking_number: str
    ) -> bool:
        """배송 정보 업데이트"""
        
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/orders/{marketplace_order_id}/shipment"
        url = f"{self.base_url}{path}"
        
        # 택배사 코드 매핑
        carrier_code = self._get_carrier_code(carrier)
        
        data = {
            "vendorId": self.vendor_id,
            "orderId": marketplace_order_id,
            "deliveryCompanyCode": carrier_code,
            "invoiceNumber": tracking_number,
            "splitShipping": False
        }
        
        headers = self._create_auth_headers("POST", path, data)
        
        response = await self.client.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get("code") == "SUCCESS"
        
        return False
    
    def _create_auth_headers(
        self,
        method: str,
        path: str,
        params: Dict[str, Any]
    ) -> Dict[str, str]:
        """쿠팡 API 인증 헤더 생성"""
        
        # Query string 생성
        query_parts = []
        for key in sorted(params.keys()):
            query_parts.append(f"{key}={params[key]}")
        query_string = "&".join(query_parts)
        
        # 현재 시간
        datetime_str = time.strftime('%y%m%d')
        timestamp = str(int(time.time() * 1000))
        
        # Message 생성
        message = f"{datetime_str}~{method}~{path}~{query_string}"
        
        # Signature 생성
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Authorization header
        auth_header = (
            f"CEA algorithm=HmacSHA256, "
            f"access-key={self.api_key}, "
            f"signed-date={datetime_str}, "
            f"signature={signature}"
        )
        
        return {
            "Authorization": auth_header,
            "X-Requested-By": self.vendor_id,
            "Content-Type": "application/json;charset=UTF-8"
        }
    
    def _parse_options(self, item: Dict[str, Any]) -> Dict[str, str]:
        """옵션 정보 파싱"""
        options = {}
        
        # 쿠팡은 옵션을 vendorItemName에 포함
        vendor_item_name = item.get("vendorItemName", "")
        if " - " in vendor_item_name:
            option_str = vendor_item_name.split(" - ", 1)[1]
            # 예: "색상: 블랙, 사이즈: L"
            for opt in option_str.split(", "):
                if ": " in opt:
                    key, value = opt.split(": ", 1)
                    options[key] = value
        
        return options
    
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
    
    def _get_order_status(self, raw_order: Dict[str, Any]) -> OrderStatus:
        """주문 전체 상태 결정"""
        # 모든 아이템의 상태를 확인
        items = raw_order.get("orderItems", [])
        if not items:
            return OrderStatus.PENDING
        
        statuses = [item.get("status") for item in items]
        
        # 하나라도 취소면 취소
        if "CANCEL" in statuses:
            return OrderStatus.CANCELLED
        
        # 모두 배송완료면 완료
        if all(s in ["FINAL_DELIVERY", "NONE_TRACKING"] for s in statuses):
            return OrderStatus.DELIVERED
        
        # 하나라도 배송중이면 배송중
        if any(s in ["DEPARTURE", "DELIVERING"] for s in statuses):
            return OrderStatus.SHIPPED
        
        # 준비중
        if any(s == "INSTRUCT" for s in statuses):
            return OrderStatus.PREPARING
        
        # 확인됨
        if all(s == "ACCEPT" for s in statuses):
            return OrderStatus.CONFIRMED
        
        return OrderStatus.PENDING
    
    def _get_delivery_status(self, raw_order: Dict[str, Any]) -> DeliveryStatus:
        """배송 상태 결정"""
        status = raw_order.get("status", "")
        
        if status in ["DEPARTURE", "DELIVERING"]:
            return DeliveryStatus.IN_TRANSIT
        elif status in ["FINAL_DELIVERY", "NONE_TRACKING"]:
            return DeliveryStatus.DELIVERED
        elif status == "INSTRUCT":
            return DeliveryStatus.PREPARING
        else:
            return DeliveryStatus.PENDING
    
    def _get_coupang_status(self, status: OrderStatus) -> Optional[str]:
        """OrderStatus를 쿠팡 상태로 변환"""
        reverse_mapping = {v: k for k, v in self.status_mapping.items()}
        return reverse_mapping.get(status)
    
    def _get_carrier_code(self, carrier_name: str) -> str:
        """택배사 이름을 코드로 변환"""
        carrier_codes = {
            "CJ대한통운": "CJGLS",
            "한진택배": "HANJIN",
            "롯데택배": "LOTTE",
            "로젠택배": "LOGEN",
            "우체국택배": "EPOST",
            "대한통운": "CJGLS",
            "경동택배": "KDEXP",
            "CVS편의점택배": "CVSNET"
        }
        return carrier_codes.get(carrier_name, "ETC")
    
    async def _confirm_order(self, marketplace_order_id: str) -> bool:
        """주문 확인"""
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/orders/{marketplace_order_id}/confirm"
        url = f"{self.base_url}{path}"
        
        headers = self._create_auth_headers("PUT", path, {})
        
        response = await self.client.put(url, headers=headers)
        return response.status_code == 200
    
    async def _cancel_order(self, marketplace_order_id: str) -> bool:
        """주문 취소"""
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/orders/{marketplace_order_id}/cancel"
        url = f"{self.base_url}{path}"
        
        data = {
            "vendorId": self.vendor_id,
            "orderId": marketplace_order_id,
            "cancelReasonCategory": "ETC",
            "cancelReasonDetail": "고객 요청"
        }
        
        headers = self._create_auth_headers("PUT", path, data)
        
        response = await self.client.put(url, json=data, headers=headers)
        return response.status_code == 200
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()