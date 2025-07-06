"""
쿠팡 주문 관리자
쿠팡 WING API를 통한 주문 조회 및 관리
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from dropshipping.models.order import (
    CustomerInfo,
    DeliveryInfo,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    PaymentInfo,
    PaymentMethod,
    PaymentStatus,
)
from dropshipping.orders.base import BaseOrderManager, OrderManagerType
from dropshipping.storage.base import BaseStorage


class CoupangOrderManager(BaseOrderManager):
    """쿠팡 주문 관리자"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(OrderManagerType.COUPANG, storage, config)
        self.vendor_id = self.config.get("vendor_id", "")
        self.test_mode = self.config.get("test_mode", False)
        self.base_url = (
            "https://api-gateway-it.coupang.com"
            if self.test_mode
            else "https://api-gateway.coupang.com"
        )
        self.client = httpx.AsyncClient(timeout=30.0)
        self.status_mapping = {
            "ACCEPT": OrderStatus.CONFIRMED,
            "INSTRUCT": OrderStatus.PREPARING,
            "DEPARTURE": OrderStatus.SHIPPED,
            "DELIVERING": OrderStatus.SHIPPED,
            "FINAL_DELIVERY": OrderStatus.DELIVERED,
            "NONE_TRACKING": OrderStatus.DELIVERED,
            "CANCEL": OrderStatus.CANCELLED,
        }
        self.payment_status_mapping = {
            "PAY_SUCCESS": PaymentStatus.COMPLETED,
            "PAY_FAIL": PaymentStatus.FAILED,
            "PAY_CANCEL": PaymentStatus.CANCELLED,
            "REFUND_SUCCESS": PaymentStatus.REFUNDED,
        }
        self.payment_method_mapping = {
            "CREDIT_CARD": PaymentMethod.CARD,
            "BANK_TRANSFER": PaymentMethod.BANK,
            "VIRTUAL_ACCOUNT": PaymentMethod.VIRTUAL_ACCOUNT,
            "PHONE": PaymentMethod.PHONE,
            "CASH": PaymentMethod.CASH,
        }

    async def _api_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """중앙 API 요청 핸들러"""
        url = f"{self.base_url}{path}"
        params = params or {}
        body_str = json.dumps(data) if data else ""

        headers = self._create_auth_headers(method, path, params, body_str)

        for attempt in range(self.max_retries):
            try:
                response = await self.client.request(
                    method, url, params=params, content=body_str, headers=headers
                )
                response.raise_for_status()
                response_data = response.json()

                if response_data.get("code") == "SUCCESS":
                    logger.debug(f"API 요청 성공: {method} {path}")
                    return response_data
                else:
                    error_message = response_data.get("message", "Unknown error")
                    raise Exception(f"Coupang API Error: {error_message}")

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"API 요청 실패 (시도 {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(5)
        raise Exception("API 요청 최종 실패")

    async def fetch_orders(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Dict[str, Any]]:
        """주문 목록 조회"""
        if not end_date:
            end_date = datetime.now()
        if (end_date - start_date).days > 31:
            raise ValueError("조회 기간은 31일을 초과할 수 없습니다")

        params = {
            "createdAtFrom": start_date.strftime("%Y-%m-%d"),
            "createdAtTo": end_date.strftime("%Y-%m-%d"),
            "status": "ALL",
            "maxPerPage": 50,
        }
        if status and (coupang_status := self._get_coupang_status(status)):
            params["status"] = coupang_status

        all_orders = []
        next_token = None
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets"

        while True:
            request_params = {**params, "vendorId": self.vendor_id}
            if next_token:
                request_params["nextToken"] = next_token

            response = await self._api_request("GET", path, params=request_params)
            orders = response.get("data", [])
            all_orders.extend(orders)

            next_token = response.get("nextToken")
            if not next_token:
                break

        logger.info(f"쿠팡 주문 {len(all_orders)}건 조회 완료")
        return all_orders

    async def fetch_order_detail(self, marketplace_order_id: str) -> Dict[str, Any]:
        """주문 상세 조회"""
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{marketplace_order_id}"
        response = await self._api_request("GET", path, params={"vendorId": self.vendor_id})
        return response.get("data", {})

    async def transform_order(self, raw_order: Dict[str, Any]) -> Order:
        """주문 데이터 변환"""
        order_id = f"CP{raw_order['orderId']}"
        items = [
            OrderItem(
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
                status=self.status_mapping.get(item.get("status"), OrderStatus.PENDING),
            )
            for idx, item in enumerate(raw_order.get("orderItems", []))
        ]
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
            marketplace_customer_id=raw_order.get("customerId"),
        )
        payment = PaymentInfo(
            method=self.payment_method_mapping.get(
                raw_order.get("paymentMethod", "CREDIT_CARD"), PaymentMethod.CARD
            ),
            status=self.payment_status_mapping.get(
                raw_order.get("paymentStatus"), PaymentStatus.PENDING
            ),
            total_amount=Decimal(str(raw_order.get("totalPaidAmount", 0))),
            product_amount=Decimal(str(raw_order.get("totalPaidAmount", 0)))
            - Decimal(str(raw_order.get("shippingPrice", 0))),
            shipping_fee=Decimal(str(raw_order.get("shippingPrice", 0))),
            discount_amount=Decimal(str(raw_order.get("discountPrice", 0))),
            transaction_id=raw_order.get("paymentTransactionId"),
            paid_at=self._parse_datetime(raw_order.get("paidAt")),
        )
        delivery = DeliveryInfo(
            status=self._get_delivery_status(raw_order),
            carrier=raw_order.get("deliveryCompanyName"),
            tracking_number=raw_order.get("invoiceNumber"),
            shipped_at=self._parse_datetime(raw_order.get("shippedAt")),
            delivered_at=self._parse_datetime(raw_order.get("deliveredAt")),
            estimated_delivery=self._parse_datetime(raw_order.get("estimatedDeliveryDate")),
        )
        return Order(
            id=order_id,
            marketplace=self.marketplace.value,
            marketplace_order_id=str(raw_order["orderId"]),
            order_date=self._parse_datetime(raw_order["orderedAt"]),
            status=self._get_order_status(raw_order),
            items=items,
            customer=customer,
            payment=payment,
            delivery=delivery,
            raw_data=raw_order,
        )

    async def update_order_status(self, marketplace_order_id: str, status: OrderStatus) -> bool:
        if status == OrderStatus.CANCELLED:
            return await self._cancel_order(marketplace_order_id)
        elif status == OrderStatus.PREPARING:
            return await self._confirm_order(marketplace_order_id)
        logger.warning(f"지원하지 않는 상태 업데이트: {status}")
        return False

    async def update_tracking_info(
        self, marketplace_order_id: str, carrier: str, tracking_number: str
    ) -> bool:
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/orders/{marketplace_order_id}/shipment"
        payload = {
            "vendorId": self.vendor_id,
            "orderId": marketplace_order_id,
            "deliveryCompanyCode": self._get_carrier_code(carrier),
            "invoiceNumber": tracking_number,
        }
        try:
            await self._api_request("POST", path, data=payload)
            return True
        except Exception as e:
            logger.error(f"송장 업데이트 실패: {e}")
            return False

    def _create_auth_headers(
        self, method: str, path: str, query_params: Dict[str, Any], body: str
    ) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        datetime_str = now.strftime("%y%m%d")
        # Coupang wants 'YYYY-MM-DDTHH:MM:SSZ' format for the signature timestamp
        timestamp_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')

        query_string = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
        message = f"{datetime_str}T{timestamp_str}{method.upper()}{path}{query_string}{body}"

        signature = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # The Authorization header format is slightly different from the signature message
        auth_datetime_str = now.strftime('%y%m%d')
        auth_timestamp_str = now.strftime('%H%M%S')

        return {
            "Authorization": f"CEA algorithm=HmacSHA256, access-key={self.api_key}, signed-date={auth_datetime_str}T{auth_timestamp_str}Z, signature={signature}",
            "X-Requested-By": self.vendor_id,
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _parse_options(self, item: Dict[str, Any]) -> Dict[str, str]:
        options = {}
        vendor_item_name = item.get("vendorItemName", "")
        if " - " in vendor_item_name:
            parts = vendor_item_name.split(" - ", 1)
            if len(parts) > 1:
                option_str = parts[1]
                for opt in option_str.split(", "):
                    if ": " in opt:
                        key, value = opt.split(": ", 1)
                        options[key] = value
        return options

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str: return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _get_order_status(self, raw_order: Dict[str, Any]) -> OrderStatus:
        statuses = {item.get("status") for item in raw_order.get("orderItems", [])}
        if not statuses: return OrderStatus.PENDING
        if "CANCEL" in statuses: return OrderStatus.CANCELLED
        if statuses <= {"FINAL_DELIVERY", "NONE_TRACKING"}: return OrderStatus.DELIVERED
        if "DEPARTURE" in statuses or "DELIVERING" in statuses: return OrderStatus.SHIPPED
        if "INSTRUCT" in statuses: return OrderStatus.PREPARING
        if statuses <= {"ACCEPT"}: return OrderStatus.CONFIRMED
        return OrderStatus.PENDING

    def _get_delivery_status(self, raw_order: Dict[str, Any]) -> DeliveryStatus:
        order_status = self._get_order_status(raw_order)
        if order_status == OrderStatus.SHIPPED: return DeliveryStatus.IN_TRANSIT
        if order_status == OrderStatus.DELIVERED: return DeliveryStatus.DELIVERED
        if order_status == OrderStatus.PREPARING: return DeliveryStatus.PREPARING
        return DeliveryStatus.PENDING

    def _get_coupang_status(self, status: OrderStatus) -> Optional[str]:
        return next((k for k, v in self.status_mapping.items() if v == status), None)

    async def _cancel_order(self, marketplace_order_id: str) -> bool:
        logger.warning(f"쿠팡 주문 취소는 WING에서 직접 처리해야 합니다: {marketplace_order_id}")
        return False

    async def _confirm_order(self, marketplace_order_id: str) -> bool:
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/orders/{marketplace_order_id}/acknowledgement"
        payload = {"vendorId": self.vendor_id, "orderId": marketplace_order_id}
        try:
            # API 요청 시 params와 data를 명확히 전달
            await self._api_request("PUT", path, params={}, data=payload)
            return True
        except Exception as e:
            logger.error(f"주문 확인(발주) 실패: {e}")
            return False

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
            "CVS편의점택배": "CVSNET",
        }
        return carrier_codes.get(carrier_name, "ETC")

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
