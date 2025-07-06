"""
11번가 주문 관리자
11번가 OpenAPI를 통한 주문 조회 및 관리
"""

import xml.etree.ElementTree as ET
from datetime import datetime
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


class ElevenstOrderManager(BaseOrderManager):
    """11번가 주문 관리자"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 11번가 API 설정
        """
        super().__init__(OrderManagerType.ELEVENST, storage, config)

        # API URL
        self.base_url = "https://api.11st.co.kr"

        # HTTP 클라이언트
        self.client = httpx.AsyncClient(timeout=30.0)

        # 주문 상태 매핑
        self.status_mapping = {
            "100": OrderStatus.PENDING,  # 입금대기
            "110": OrderStatus.CONFIRMED,  # 결제완료
            "120": OrderStatus.PREPARING,  # 배송준비중
            "130": OrderStatus.SHIPPED,  # 배송중
            "140": OrderStatus.DELIVERED,  # 배송완료
            "201": OrderStatus.CANCELLED,  # 취소신청
            "202": OrderStatus.CANCELLED,  # 취소완료
            "301": OrderStatus.REFUNDED,  # 반품신청
            "302": OrderStatus.REFUNDED,  # 반품완료
            "401": OrderStatus.EXCHANGED,  # 교환신청
            "402": OrderStatus.EXCHANGED,  # 교환완료
        }

        # 결제 방법 매핑
        self.payment_method_mapping = {
            "SC0010": PaymentMethod.CARD,  # 신용카드
            "SC0030": PaymentMethod.BANK,  # 계좌이체
            "SC0040": PaymentMethod.VIRTUAL_ACCOUNT,  # 가상계좌
            "SC0060": PaymentMethod.PHONE,  # 휴대폰
            "SC0100": PaymentMethod.POINT,  # OK캐쉬백
        }

    async def _api_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
    ) -> ET.Element:
        """중앙 API 요청 핸들러"""
        url = f"{self.base_url}{path}"
        headers = {"openapikey": self.api_key, "Content-Type": "application/xml"}

        for attempt in range(self.max_retries):
            try:
                response = await self.client.request(
                    method, url, params=params, content=data, headers=headers
                )
                response.raise_for_status()
                root = ET.fromstring(response.text)

                error_element = root if root.tag == "ErrorMessage" else root.find("ErrorMessage")

                if error_element is not None:
                    message_element = error_element.find("message")
                    error_text = "Unknown error"
                    if message_element is not None and message_element.text:
                        error_text = message_element.text.strip()

                    raise Exception(f"11st API Error: {error_text}")

                logger.debug(f"API 요청 성공: {method} {path}")
                return root

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
        if (end_date - start_date).days > 90:
            raise ValueError("조회 기간은 90일을 초과할 수 없습니다")

        params = {
            "startDate": start_date.strftime("%Y%m%d"),
            "endDate": end_date.strftime("%Y%m%d"),
            "dataType": "xml",
        }
        if status and (elevenst_status := self._get_elevenst_status(status)):
            params["orderStatusCd"] = elevenst_status

        root = await self._api_request("GET", "/openapi/v1/orders", params=params)

        orders = [self._xml_to_dict(order_elem) for order_elem in root.findall(".//order")]

        logger.info(f"11번가 주문 {len(orders)}건 조회 완료")
        return orders

    async def fetch_order_detail(self, marketplace_order_id: str) -> Dict[str, Any]:
        """주문 상세 조회"""
        path = f"/openapi/v1/orders/{marketplace_order_id}"
        root = await self._api_request("GET", path)

        order_elem = root.find(".//order")
        if order_elem is None:
            raise Exception("주문 정보를 찾을 수 없습니다")

        return self._xml_to_dict(order_elem)

    async def transform_order(self, raw_order: Dict[str, Any]) -> Order:
        """주문 데이터 변환"""

        # 주문 ID 생성
        order_id = f"11ST{raw_order.get('ordNo', '')}"

        # 주문 항목 변환
        items = []
        order_products = raw_order.get("orderProduct", [])
        if not isinstance(order_products, list):
            order_products = [order_products]

        for idx, item in enumerate(order_products):
            # 옵션 정보 파싱
            options = {}
            sel_no = item.get("selNo", "")
            if " / " in sel_no:
                for opt in sel_no.split(" / "):
                    if " : " in opt:
                        key, value = opt.split(" : ", 1)
                        options[key] = value

            order_item = OrderItem(
                id=f"{order_id}_ITEM{idx+1}",
                product_id=item.get("prdNo", ""),
                marketplace_product_id=item.get("prdNo", ""),
                supplier_product_id="",  # 11번가는 공급사 코드 미제공
                product_name=item.get("prdNm", ""),
                variant_id=item.get("selPrdNo"),
                options=options,
                quantity=int(item.get("ordCnt", 1)),
                unit_price=Decimal(str(item.get("selPrc", 0))),
                total_price=Decimal(str(item.get("selPrc", 0))) * int(item.get("ordCnt", 1)),
                discount_amount=Decimal(str(item.get("promDscPrc", 0))),
                status=self.status_mapping.get(item.get("ordPrdStat"), OrderStatus.PENDING),
            )
            items.append(order_item)

        # 배송지 정보
        delivery_info = raw_order.get("deliveryInfo", {})

        # 고객 정보
        customer = CustomerInfo(
            name=raw_order.get("ordNm", ""),
            phone=raw_order.get("ordPrtblTel", ""),
            email=raw_order.get("ordEmail"),
            recipient_name=delivery_info.get("rcvrNm", ""),
            recipient_phone=delivery_info.get("rcvrPrtblTel", ""),
            postal_code=delivery_info.get("rcvrPostNo", ""),
            address=delivery_info.get("rcvrBaseAddr", ""),
            address_detail=delivery_info.get("rcvrDtlsAddr"),
            delivery_message=delivery_info.get("dlvMemo"),
            marketplace_customer_id=raw_order.get("memNo"),
        )

        # 결제 정보
        payment = PaymentInfo(
            method=self.payment_method_mapping.get(
                raw_order.get("sttlmtMthdCd", "SC0010"), PaymentMethod.CARD
            ),
            status=self._get_payment_status(raw_order),
            total_amount=Decimal(str(raw_order.get("ordAmt", 0))),
            product_amount=Decimal(str(raw_order.get("ordAmt", 0)))
            - Decimal(str(raw_order.get("dlvCst", 0))),
            shipping_fee=Decimal(str(raw_order.get("dlvCst", 0))),
            discount_amount=Decimal(str(raw_order.get("dscAmt", 0))),
            transaction_id=raw_order.get("ordNo"),
            paid_at=self._parse_datetime(raw_order.get("ordDt")),
        )

        # 배송 정보
        delivery = DeliveryInfo(
            status=self._get_delivery_status(raw_order),
            carrier=delivery_info.get("dlvEtprsCd"),
            tracking_number=delivery_info.get("invcNo"),
            shipped_at=self._parse_datetime(delivery_info.get("dlvDt")),
            delivered_at=self._parse_datetime(delivery_info.get("dlvCpltDt")),
            estimated_delivery=None,  # 11번가는 예상 배송일 미제공
        )

        # 주문 생성
        order = Order(
            id=order_id,
            marketplace=self.marketplace.value,
            marketplace_order_id=raw_order.get("ordNo", ""),
            order_date=self._parse_datetime(raw_order.get("ordDt")),
            status=self._get_order_status(raw_order),
            items=items,
            customer=customer,
            payment=payment,
            delivery=delivery,
            raw_data=raw_order,
        )

        return order

    async def update_order_status(self, marketplace_order_id: str, status: OrderStatus) -> bool:
        """주문 상태 업데이트"""

        # 11번가는 취소/반품/교환만 API 지원
        if status == OrderStatus.CANCELLED:
            return await self._cancel_order(marketplace_order_id)
        elif status == OrderStatus.REFUNDED:
            return await self._return_order(marketplace_order_id)
        else:
            logger.warning(f"지원하지 않는 상태 업데이트: {status}")
            return False

    async def update_tracking_info(
        self, marketplace_order_id: str, carrier: str, tracking_number: str
    ) -> bool:
        """배송 정보 업데이트"""
        path = f"/openapi/v1/orders/{marketplace_order_id}/delivery"
        carrier_code = self._get_carrier_code(carrier)
        xml_data = f'<?xml version="1.0" encoding="UTF-8"?><deliveryInfo><dlvEtprsCd>{carrier_code}</dlvEtprsCd><invcNo>{tracking_number}</invcNo></deliveryInfo>'

        try:
            root = await self._api_request("PUT", path, data=xml_data)
            result = root.find(".//resultCode")
            return result is not None and result.text == "0"
        except Exception as e:
            logger.error(f"송장 업데이트 실패: {e}")
            return False

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """XML 요소를 딕셔너리로 변환"""
        result = {}

        # 속성
        if element.attrib:
            result.update(element.attrib)

        # 텍스트
        if element.text and element.text.strip():
            if len(element) == 0:  # 자식 요소가 없으면
                return element.text.strip()
            else:
                result["_text"] = element.text.strip()

        # 자식 요소
        children = {}
        for child in element:
            child_data = self._xml_to_dict(child)

            if child.tag in children:
                # 이미 존재하면 리스트로 변환
                if not isinstance(children[child.tag], list):
                    children[child.tag] = [children[child.tag]]
                children[child.tag].append(child_data)
            else:
                children[child.tag] = child_data

        result.update(children)

        return result

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not date_str:
            return None

        try:
            # YYYYMMDDHHmmss 형식
            if len(date_str) == 14:
                return datetime.strptime(date_str, "%Y%m%d%H%M%S")
            # YYYYMMDD 형식
            elif len(date_str) == 8:
                return datetime.strptime(date_str, "%Y%m%d")
            else:
                return None
        except:
            return None

    def _get_order_status(self, raw_order: Dict[str, Any]) -> OrderStatus:
        """주문 전체 상태 결정"""
        status_code = raw_order.get("ordStat", "")
        return self.status_mapping.get(status_code, OrderStatus.PENDING)

    def _get_payment_status(self, raw_order: Dict[str, Any]) -> PaymentStatus:
        """결제 상태 결정"""
        order_status = raw_order.get("ordStat", "")

        if order_status in ["110", "120", "130", "140"]:
            return PaymentStatus.COMPLETED
        elif order_status in ["201", "202"]:
            return PaymentStatus.CANCELLED
        elif order_status in ["301", "302"]:
            return PaymentStatus.REFUNDED
        else:
            return PaymentStatus.PENDING

    def _get_delivery_status(self, raw_order: Dict[str, Any]) -> DeliveryStatus:
        """배송 상태 결정"""
        order_status = raw_order.get("ordStat", "")

        if order_status == "120":
            return DeliveryStatus.PREPARING
        elif order_status == "130":
            return DeliveryStatus.IN_TRANSIT
        elif order_status == "140":
            return DeliveryStatus.DELIVERED
        else:
            return DeliveryStatus.PENDING

    def _get_elevenst_status(self, status: OrderStatus) -> Optional[str]:
        """OrderStatus를 11번가 상태 코드로 변환"""
        reverse_mapping = {v: k for k, v in self.status_mapping.items()}
        return reverse_mapping.get(status)

    def _get_carrier_code(self, carrier_name: str) -> str:
        """택배사 이름을 코드로 변환"""
        carrier_codes = {
            "CJ대한통운": "00034",
            "한진택배": "00011",
            "롯데택배": "00012",
            "로젠택배": "00008",
            "우체국택배": "00001",
            "대한통운": "00034",
            "경동택배": "00026",
            "CVS편의점택배": "00093",
            "CU편의점택배": "00094",
            "GS편의점택배": "00095",
        }
        return carrier_codes.get(carrier_name, "00099")  # 기타

    async def _cancel_order(self, marketplace_order_id: str) -> bool:
        """주문 취소"""
        path = f"/openapi/v1/orders/{marketplace_order_id}/cancel"
        xml_data = '<?xml version="1.0" encoding="UTF-8"?><cancelInfo><cancelReasonCd>100</cancelReasonCd><cancelReasonDetail>고객 요청에 의한 취소</cancelReasonDetail></cancelInfo>'

        try:
            root = await self._api_request("POST", path, data=xml_data)
            result = root.find(".//resultCode")
            return result is not None and result.text == "0"
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return False

    async def _return_order(self, marketplace_order_id: str) -> bool:
        """주문 반품"""
        path = f"/openapi/v1/orders/{marketplace_order_id}/return"
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <returnInfo>
            <returnReasonCd>200</returnReasonCd>
            <returnReasonDetail>상품 불량</returnReasonDetail>
        </returnInfo>"""

        try:
            root = await self._api_request("POST", path, data=xml_data)
            result = root.find(".//resultCode")
            return result is not None and result.text == "0"
        except Exception as e:
            logger.error(f"주문 반품 실패: {e}")
            return False

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
