"""
주문 관리자 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from dropshipping.models.order import (
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
)
from dropshipping.orders.coupang import CoupangOrderManager
from dropshipping.orders.elevenst import ElevenstOrderManager
from dropshipping.orders.naver import SmartstoreOrderManager
from dropshipping.storage.base import BaseStorage


class MockStorage(BaseStorage):
    """테스트용 Mock Storage"""

    def __init__(self):
        super().__init__()
        self.data = {}
        self.id_counter = 1

    async def create(self, table: str, data: dict) -> dict:
        if table not in self.data:
            self.data[table] = {}

        data["id"] = str(self.id_counter)
        self.id_counter += 1
        data["created_at"] = datetime.now()
        data["updated_at"] = datetime.now()

        self.data[table][data["id"]] = data
        return data

    async def get(self, table: str, id: str = None, filters: dict = None) -> dict:
        if table not in self.data:
            return None

        if id:
            return self.data[table].get(id)

        if filters:
            for item in self.data[table].values():
                match = True
                for key, value in filters.items():
                    if item.get(key) != value:
                        match = False
                        break
                if match:
                    return item

        return None

    async def list(self, table: str, filters: dict = None, limit: int = None) -> list:
        if table not in self.data:
            return []

        items = list(self.data[table].values())

        if filters:
            filtered_items = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if isinstance(value, dict):
                        # 복잡한 필터 처리 (예: $nin, $in)
                        if "$nin" in value and item.get(key) in value["$nin"]:
                            match = False
                            break
                        if "$in" in value and item.get(key) not in value["$in"]:
                            match = False
                            break
                    elif item.get(key) != value:
                        match = False
                        break
                if match:
                    filtered_items.append(item)
            items = filtered_items

        if limit:
            items = items[:limit]

        return items

    async def update(self, table: str, id: str, data: dict) -> dict:
        if table not in self.data or id not in self.data[table]:
            return None

        self.data[table][id].update(data)
        self.data[table][id]["updated_at"] = datetime.now()
        return self.data[table][id]

    async def delete(self, table: str, id: str) -> bool:
        if table not in self.data or id not in self.data[table]:
            return False

        del self.data[table][id]
        return True

    # BaseStorage 추상 메서드 구현
    async def save_raw_product(self, supplier: str, product_data: dict) -> dict:
        return await self.create("raw_products", product_data)

    async def save_processed_product(self, product_data: dict) -> dict:
        return await self.create("products", product_data)

    async def get_raw_product(self, supplier: str, product_id: str) -> dict:
        return await self.get(
            "raw_products", filters={"supplier": supplier, "product_id": product_id}
        )

    async def get_processed_product(self, product_id: str) -> dict:
        return await self.get("products", product_id)

    async def list_raw_products(self, supplier: str, limit: int = 100) -> list:
        return await self.list("raw_products", filters={"supplier": supplier}, limit=limit)

    async def update_status(self, supplier: str, product_id: str, status: str) -> bool:
        product = await self.get_raw_product(supplier, product_id)
        if product:
            await self.update("raw_products", product["id"], {"status": status})
            return True
        return False

    async def exists_by_hash(self, data_hash: str) -> bool:
        products = await self.list("raw_products")
        return any(p.get("data_hash") == data_hash for p in products)

    async def get_stats(self, supplier: str) -> dict:
        products = await self.list("raw_products", filters={"supplier": supplier})
        return {
            "total": len(products),
            "processed": len([p for p in products if p.get("status") == "processed"]),
            "failed": len([p for p in products if p.get("status") == "failed"]),
        }
    
    # 누락된 추상 메서드들 구현
    def get_pricing_rules(self, active_only: bool = True) -> list:
        """가격 규칙 목록 반환"""
        return []
    
    def get_all_category_mappings(self) -> list:
        """카테고리 매핑 목록 반환"""
        return []
    
    def get_supplier_code(self, supplier_name: str) -> str:
        """공급사 코드 반환"""
        return supplier_name.upper()
    
    def get_marketplace_code(self, marketplace_name: str) -> str:
        """마켓플레이스 코드 반환"""
        return marketplace_name.upper()
    
    def save_marketplace_upload(self, data: dict) -> dict:
        """마켓플레이스 업로드 정보 저장"""
        return {"id": 1, **data}
    
    def get_marketplace_upload(self, product_id: str, marketplace: str) -> dict:
        """마켓플레이스 업로드 정보 조회"""
        return None
    
    def upsert(self, table: str, data: dict, unique_fields: list) -> dict:
        """Upsert 작업 수행"""
        return {"id": 1, **data}


class TestCoupangOrderManager:
    """쿠팡 주문 관리자 테스트"""

    @pytest.fixture
    def storage(self):
        return MockStorage()

    @pytest.fixture
    def manager(self, storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "vendor_id": "test_vendor",
            "test_mode": True,
        }
        return CoupangOrderManager(storage, config)

    def test_init(self, manager):
        """초기화 테스트"""
        assert manager.marketplace.value == "coupang"
        assert manager.vendor_id == "test_vendor"
        assert manager.test_mode is True
        assert "api-gateway-it.coupang.com" in manager.base_url

    @patch("httpx.AsyncClient.get")
    def test_fetch_orders(self, mock_get, manager):
        """주문 목록 조회 테스트"""
        # Mock 응답
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": [
                {
                    "orderId": "123456",
                    "orderedAt": "2024-01-01T10:00:00Z",
                    "orderItems": [
                        {
                            "sellerProductId": "PROD001",
                            "productId": 12345,
                            "sellerProductName": "테스트 상품",
                            "orderPrice": 10000,
                            "shippingCount": 1,
                            "status": "ACCEPT",
                        }
                    ],
                    "ordererName": "홍길동",
                    "ordererPhoneNumber": "010-1234-5678",
                    "receiverName": "홍길동",
                    "receiverPhoneNumber1": "010-1234-5678",
                    "receiverPostCode": "12345",
                    "receiverAddr1": "서울시 강남구",
                    "receiverAddr2": "테스트동 123",
                    "totalPaidAmount": 12500,
                    "shippingPrice": 2500,
                }
            ],
        }
        mock_get.return_value = mock_response

        # 실행
        start_date = datetime.now() - timedelta(days=1)
        orders = asyncio.run(manager.fetch_orders(start_date))

        # 검증
        assert len(orders) == 1
        assert orders[0]["orderId"] == "123456"
        assert orders[0]["orderItems"][0]["sellerProductName"] == "테스트 상품"

    def test_transform_order(self, manager):
        """주문 데이터 변환 테스트"""
        raw_order = {
            "orderId": "123456",
            "orderedAt": "2024-01-01T10:00:00Z",
            "orderItems": [
                {
                    "sellerProductId": "PROD001",
                    "productId": 12345,
                    "sellerProductName": "테스트 상품",
                    "vendorItemId": "VENDOR001",
                    "vendorItemName": "테스트 상품 - 색상: 블랙, 사이즈: L",
                    "orderPrice": 10000,
                    "shippingCount": 1,
                    "discountPrice": 1000,
                    "status": "ACCEPT",
                }
            ],
            "ordererName": "홍길동",
            "ordererPhoneNumber": "010-1234-5678",
            "receiverName": "홍길동",
            "receiverPhoneNumber1": "010-1234-5678",
            "receiverPostCode": "12345",
            "receiverAddr1": "서울시 강남구",
            "receiverAddr2": "테스트동 123",
            "totalPaidAmount": 11500,
            "shippingPrice": 2500,
            "discountPrice": 1000,
            "paymentMethod": "CREDIT_CARD",
        }

        # 실행
        order = asyncio.run(manager.transform_order(raw_order))

        # 검증
        assert order.id == "CP123456"
        assert order.marketplace == "coupang"
        assert order.marketplace_order_id == "123456"
        assert len(order.items) == 1
        assert order.items[0].product_name == "테스트 상품"
        assert order.items[0].options == {"색상": "블랙", "사이즈": "L"}
        assert order.items[0].unit_price == Decimal("10000")
        assert order.customer.name == "홍길동"
        assert order.payment.total_amount == Decimal("11500")
        assert order.payment.shipping_fee == Decimal("2500")
        assert order.status == OrderStatus.CONFIRMED

    @patch("httpx.AsyncClient.post")
    def test_update_tracking_info(self, mock_post, manager):
        """배송 정보 업데이트 테스트"""
        # Mock 응답
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": "SUCCESS"}
        mock_post.return_value = mock_response

        # 실행
        success = asyncio.run(manager.update_tracking_info("123456", "CJ대한통운", "1234567890"))

        # 검증
        assert success is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "shipment" in call_args[0][0]
        assert call_args[1]["json"]["deliveryCompanyCode"] == "CJGLS"
        assert call_args[1]["json"]["invoiceNumber"] == "1234567890"


class TestElevenstOrderManager:
    """11번가 주문 관리자 테스트"""

    @pytest.fixture
    def storage(self):
        return MockStorage()

    @pytest.fixture
    def manager(self, storage):
        config = {"api_key": "test_key"}
        return ElevenstOrderManager(storage, config)

    def test_init(self, manager):
        """초기화 테스트"""
        assert manager.marketplace.value == "11st"
        assert manager.base_url == "https://api.11st.co.kr"

    def test_xml_to_dict(self, manager):
        """XML 변환 테스트"""
        import xml.etree.ElementTree as ET

        xml_str = """
        <order>
            <ordNo>123456</ordNo>
            <ordNm>홍길동</ordNm>
            <orderProduct>
                <prdNo>PROD001</prdNo>
                <prdNm>테스트 상품</prdNm>
                <selPrc>10000</selPrc>
                <ordCnt>1</ordCnt>
            </orderProduct>
        </order>
        """

        root = ET.fromstring(xml_str)
        result = manager._xml_to_dict(root)

        assert result["ordNo"] == "123456"
        assert result["ordNm"] == "홍길동"
        assert result["orderProduct"]["prdNm"] == "테스트 상품"
        assert result["orderProduct"]["selPrc"] == "10000"

    def test_transform_order(self, manager):
        """주문 데이터 변환 테스트"""
        raw_order = {
            "ordNo": "123456",
            "ordDt": "20240101100000",
            "ordStat": "110",  # 결제완료
            "orderProduct": [
                {
                    "prdNo": "PROD001",
                    "prdNm": "테스트 상품",
                    "selNo": "색상 : 블랙 / 사이즈 : L",
                    "selPrc": "10000",
                    "ordCnt": "1",
                    "promDscPrc": "1000",
                    "ordPrdStat": "110",
                }
            ],
            "ordNm": "홍길동",
            "ordPrtblTel": "010-1234-5678",
            "deliveryInfo": {
                "rcvrNm": "홍길동",
                "rcvrPrtblTel": "010-1234-5678",
                "rcvrPostNo": "12345",
                "rcvrBaseAddr": "서울시 강남구",
                "rcvrDtlsAddr": "테스트동 123",
            },
            "ordAmt": "11500",
            "dlvCst": "2500",
            "dscAmt": "1000",
            "sttlmtMthdCd": "SC0010",  # 신용카드
        }

        # 실행
        order = asyncio.run(manager.transform_order(raw_order))

        # 검증
        assert order.id == "11ST123456"
        assert order.marketplace == "11st"
        assert order.marketplace_order_id == "123456"
        assert len(order.items) == 1
        assert order.items[0].product_name == "테스트 상품"
        assert order.items[0].options == {"색상": "블랙", "사이즈": "L"}
        assert order.customer.name == "홍길동"
        assert order.payment.total_amount == Decimal("11500")
        assert order.payment.method == PaymentMethod.CARD
        assert order.status == OrderStatus.CONFIRMED


class TestSmartstoreOrderManager:
    """네이버 스마트스토어 주문 관리자 테스트"""

    @pytest.fixture
    def storage(self):
        return MockStorage()

    @pytest.fixture
    def manager(self, storage):
        config = {
            "client_id": "test_client",
            "client_secret": "test_secret",
            "access_token": "test_token",
        }
        return SmartstoreOrderManager(storage, config)

    def test_init(self, manager):
        """초기화 테스트"""
        assert manager.marketplace.value == "naver"
        assert manager.base_url == "https://api.commerce.naver.com"
        assert manager.client_id == "test_client"

    def test_mask_phone(self, manager):
        """전화번호 마스킹 테스트"""
        assert manager._mask_phone("010-1234-5678") == "010****5678"
        assert manager._mask_phone("02-123-4567") == "02-****4567"
        assert manager._mask_phone("1234") == "1234"  # 짧은 번호는 그대로

    def test_transform_order(self, manager):
        """주문 데이터 변환 테스트"""
        raw_order = {
            "productOrderId": "123456",
            "order": {
                "orderDate": "2024-01-01T10:00:00Z",
                "ordererName": "홍길동",
                "ordererTel": "010-1234-5678",
                "ordererId": "user123",
                "paymentDate": "2024-01-01T10:05:00Z",
                "paymentMethod": "CARD",
            },
            "delivery": {
                "receiverName": "홍길동",
                "receiverTel1": "010-1234-5678",
                "receiverZipCode": "12345",
                "receiverAddress1": "서울시 강남구",
                "receiverAddress2": "테스트동 123",
                "deliveryMemo": "부재시 경비실",
            },
            "productId": "PROD001",
            "productName": "테스트 상품",
            "optionManageCode": "OPT001",
            "selectionTexts": ["블랙", "L사이즈"],
            "quantity": 1,
            "unitPrice": 10000,
            "totalPaymentAmount": 12500,
            "productDiscountAmount": 1000,
            "deliveryFeeAmount": 2500,
            "placeOrderStatus": "PAYED",
        }

        # 실행
        order = asyncio.run(manager.transform_order(raw_order))

        # 검증
        assert order.id == "NS123456"
        assert order.marketplace == "naver"
        assert order.marketplace_order_id == "123456"
        assert len(order.items) == 1
        assert order.items[0].product_name == "테스트 상품"
        assert order.items[0].options == {"옵션1": "블랙", "옵션2": "L사이즈"}
        assert order.customer.phone == "010****5678"  # 마스킹됨
        assert order.payment.total_amount == Decimal("12500")
        assert order.payment.method == PaymentMethod.CARD
        assert order.status == OrderStatus.CONFIRMED


class TestOrderProcessing:
    """주문 처리 통합 테스트"""

    @pytest.fixture
    def storage(self):
        return MockStorage()

    @pytest.fixture
    def coupang_manager(self, storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "vendor_id": "test_vendor",
            "test_mode": True,
        }
        return CoupangOrderManager(storage, config)

    @patch("httpx.AsyncClient.get")
    def test_process_new_orders(self, mock_get, coupang_manager, storage):
        """신규 주문 처리 테스트"""
        # Mock 응답
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": [
                {
                    "orderId": "123456",
                    "orderedAt": "2024-01-01T10:00:00Z",
                    "orderItems": [
                        {
                            "sellerProductId": "PROD001",
                            "productId": 12345,
                            "sellerProductName": "테스트 상품",
                            "orderPrice": 10000,
                            "shippingCount": 1,
                            "status": "ACCEPT",
                        }
                    ],
                    "ordererName": "홍길동",
                    "ordererPhoneNumber": "010-1234-5678",
                    "receiverName": "홍길동",
                    "receiverPhoneNumber1": "010-1234-5678",
                    "receiverPostCode": "12345",
                    "receiverAddr1": "서울시 강남구",
                    "receiverAddr2": "테스트동 123",
                    "totalPaidAmount": 12500,
                    "shippingPrice": 2500,
                }
            ],
        }
        mock_get.return_value = mock_response

        # 실행
        orders = asyncio.run(coupang_manager.process_new_orders())

        # 검증
        assert len(orders) == 1
        assert orders[0].marketplace_order_id == "123456"

        # 저장 확인
        saved_orders = asyncio.run(storage.list("orders"))
        assert len(saved_orders) == 1
        assert saved_orders[0]["marketplace_order_id"] == "123456"
        assert saved_orders[0]["marketplace"] == "coupang"

    def test_sync_order_status(self, coupang_manager, storage):
        """주문 상태 동기화 테스트"""
        # 테스트 주문 생성
        order_data = {
            "marketplace": "coupang",
            "marketplace_order_id": "123456",
            "status": OrderStatus.CONFIRMED.value,
            "delivery": {"status": DeliveryStatus.PENDING.value, "tracking_number": None},
        }
        asyncio.run(storage.create("orders", order_data))

        # Mock 상세 조회
        with patch.object(coupang_manager, "fetch_order_detail") as mock_detail:
            mock_detail.return_value = {
                "orderId": "123456",
                "orderedAt": "2024-01-01T10:00:00Z",
                "status": "DEPARTURE",  # 배송중
                "orderItems": [
                    {
                        "sellerProductId": "PROD001",
                        "productId": 12345,
                        "sellerProductName": "테스트 상품",
                        "orderPrice": 10000,
                        "shippingCount": 1,
                        "status": "DEPARTURE",
                    }
                ],
                "ordererName": "홍길동",
                "ordererPhoneNumber": "010-1234-5678",
                "receiverName": "홍길동",
                "receiverPhoneNumber1": "010-1234-5678",
                "receiverPostCode": "12345",
                "receiverAddr1": "서울시 강남구",
                "receiverAddr2": "테스트동 123",
                "totalPaidAmount": 12500,
                "shippingPrice": 2500,
                "deliveryCompanyName": "CJ대한통운",
                "invoiceNumber": "1234567890",
            }

            # 실행
            updated_count = asyncio.run(coupang_manager.sync_order_status())

            # 검증
            assert updated_count == 1

            # 업데이트 확인
            updated_order = asyncio.run(storage.get("orders", "1"))
            assert updated_order["status"] == OrderStatus.SHIPPED.value
            assert updated_order["delivery"]["tracking_number"] == "1234567890"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
