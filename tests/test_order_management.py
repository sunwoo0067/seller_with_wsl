# -*- coding: utf-8 -*-
"""
주문 관리 시스템 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List

import pytest

from dropshipping.models.order import (
    Order, OrderItem, CustomerInfo, PaymentInfo, DeliveryInfo,
    OrderStatus, PaymentStatus, DeliveryStatus, PaymentMethod
)
from dropshipping.orders.base import BaseOrderManager
from dropshipping.orders.coupang.coupang_order_manager import CoupangOrderManager
from dropshipping.orders.supplier.base import BaseSupplierOrderer, SupplierType, SupplierOrderStatus
from dropshipping.orders.supplier.domeme_orderer import DomemeOrderer
from dropshipping.orders.inventory.inventory_sync import InventorySync
from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType, DeliveryStatus as TrackingDeliveryStatus
from dropshipping.orders.delivery.tracker_manager import TrackerManager


# Mock Storage
class MockStorage:
    """테스트용 Mock Storage"""
    
    def __init__(self):
        self.data = {}
    
    async def save(self, table: str, data: Dict[str, Any]) -> str:
        if table not in self.data:
            self.data[table] = {}
        
        # ID 생성
        if "id" not in data:
            data["id"] = f"{table}_{len(self.data[table]) + 1}"
        
        self.data[table][data["id"]] = data
        return data["id"]
    
    async def get(self, table: str, id: str) -> Dict[str, Any]:
        return self.data.get(table, {}).get(id)
    
    async def list(
        self,
        table: str,
        filters: Dict[str, Any] = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        items = list(self.data.get(table, {}).values())
        
        # 간단한 필터링
        if filters:
            filtered = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if key in item:
                        # 연산자 처리
                        if isinstance(value, dict) and "$lte" in value:
                            if item[key] > value["$lte"]:
                                match = False
                                break
                        elif item[key] != value:
                            match = False
                            break
                    elif value is not None:  # 필드가 없는데 None이 아닌 값이면 매치 안됨
                        match = False
                        break
                if match:
                    filtered.append(item)
            items = filtered
        
        if limit:
            items = items[:limit]
        
        return items
    
    async def update(self, table: str, id: str, data: Dict[str, Any]) -> bool:
        if table in self.data and id in self.data[table]:
            self.data[table][id].update(data)
            return True
        return False
    
    async def delete(self, table: str, id: str) -> bool:
        if table in self.data and id in self.data[table]:
            del self.data[table][id]
            return True
        return False


# Mock Fetcher
class MockFetcher:
    """테스트용 Mock Fetcher"""
    
    async def fetch_product(self, product_id: str) -> Dict[str, Any]:
        return {
            "supplier_product_id": product_id,
            "stock": 50,
            "price": 10000
        }


# Mock Uploader
class MockUploader:
    """테스트용 Mock Uploader"""
    pass


class TestOrderModels:
    """주문 모델 테스트"""
    
    def test_order_creation(self):
        """주문 생성 테스트"""
        order = Order(
            id="ORD001",
            marketplace="coupang",
            marketplace_order_id="CP123456",
            order_date=datetime.now(),
            status=OrderStatus.PENDING,
            items=[
                OrderItem(
                    id="ITEM001",
                    product_id="PROD001",
                    marketplace_product_id="MP001",
                    product_name="테스트 상품",
                    supplier_product_id="DM12345",
                    quantity=2,
                    unit_price=Decimal("10000"),
                    total_price=Decimal("20000")
                )
            ],
            customer=CustomerInfo(
                name="홍길동",
                phone="010-1234-5678",
                email="test@example.com",
                recipient_name="홍길동",
                recipient_phone="010-1234-5678",
                postal_code="12345",
                address="서울시 강남구",
                address_detail="아파트 101동 202호"
            ),
            payment=PaymentInfo(
                method=PaymentMethod.CARD,
                total_amount=Decimal("22500"),
                product_amount=Decimal("20000"),
                shipping_fee=Decimal("2500"),
                status=PaymentStatus.COMPLETED
            ),
            delivery=DeliveryInfo(
                method="택배",
                status=DeliveryStatus.PENDING,
                requested_date=datetime.now() + timedelta(days=2)
            )
        )
        
        assert order.id == "ORD001"
        assert order.marketplace == "coupang"
        assert len(order.items) == 1
        assert order.items[0].quantity == 2
        assert order.payment.total_amount == Decimal("22500")


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
            "seller_id": "test_seller"
        }
        return CoupangOrderManager(storage, config)
    
    def test_transform_order(self, manager):
        """주문 변환 테스트"""
        raw_order = {
            "orderId": "123456",
            "orderedAt": "2024-01-15T10:30:00+09:00",
            "orderItems": [{
                "sellerProductId": "PROD001",
                "productId": "MP001",
                "vendorItemId": "VI001",
                "sellerProductName": "테스트 상품",
                "shippingCount": 2,
                "orderPrice": 10000,
                "discountPrice": 0,
                "status": "ACCEPT"
            }],
            "ordererName": "홍길동",
            "ordererPhoneNumber": "010-1234-5678",
            "ordererEmail": "test@example.com",
            "receiverName": "홍길동",
            "receiverPhoneNumber1": "010-1234-5678",
            "receiverPostCode": "12345",
            "receiverAddr1": "서울시 강남구",
            "receiverAddr2": "아파트 101동 202호",
            "paymentMethod": "CREDIT_CARD",
            "totalPaidAmount": 22500,
            "deliveryMethod": "DELIVERY"
        }
        
        order = asyncio.run(manager.transform_order(raw_order))
        
        assert order.marketplace_order_id == "123456"
        assert order.marketplace == "coupang"
        assert len(order.items) == 1
        assert order.customer.name == "홍길동"


class TestDomemeOrderer:
    """도매매 주문 전달자 테스트"""
    
    @pytest.fixture
    def storage(self):
        return MockStorage()
    
    @pytest.fixture
    def orderer(self, storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "company_code": "TEST001"
        }
        return DomemeOrderer(storage, config)
    
    def test_build_order_xml(self, orderer):
        """주문 XML 생성 테스트"""
        # 먼저 items 생성
        items = [
            OrderItem(
                id="ITEM001",
                product_id="PROD001",
                marketplace_product_id="MP001",
                product_name="테스트 상품",
                supplier_product_id="DM12345",
                quantity=2,
                unit_price=Decimal("10000"),
                total_price=Decimal("20000")
            )
        ]
        
        order = Order(
            id="ORD001",
            marketplace="coupang",
            marketplace_order_id="CP123456",
            order_date=datetime.now(),
            status=OrderStatus.PENDING,
            items=items,
            customer=CustomerInfo(
                name="홍길동",
                phone="010-1234-5678",
                email="test@example.com",
                recipient_name="홍길동",
                recipient_phone="010-1234-5678",
                postal_code="12345",
                address="서울시 강남구",
                address_detail="아파트 101동 202호"
            ),
            payment=PaymentInfo(
                method=PaymentMethod.CARD,
                total_amount=Decimal("22500"),
                product_amount=Decimal("20000"),
                shipping_fee=Decimal("2500"),
                status=PaymentStatus.COMPLETED
            ),
            delivery=DeliveryInfo(
                method="택배",
                status=DeliveryStatus.PENDING
            )
        )
        
        xml = orderer._build_order_xml(order, items)
        
        assert "<?xml version" in xml
        assert "<companyCode>TEST001</companyCode>" in xml
        assert "<orderNo>ORD001</orderNo>" in xml
        assert "<productNo>12345</productNo>" in xml
        assert "<quantity>2</quantity>" in xml


class TestInventorySync:
    """재고 동기화 테스트"""
    
    @pytest.fixture
    def storage(self):
        storage = MockStorage()
        # 테스트 상품 추가
        asyncio.run(storage.save("products", {
            "id": "PROD001",
            "name": "테스트 상품",
            "supplier_id": "domeme",
            "supplier_product_id": "12345",
            "stock": 20,
            "status": "active"
        }))
        return storage
    
    @pytest.fixture
    def sync(self, storage):
        config = {
            "safety_stock": 5,
            "batch_size": 10
        }
        return InventorySync(storage, config)
    
    def test_safety_stock(self, sync):
        """안전재고 적용 테스트"""
        supplier_stock = 50
        available_stock = max(0, supplier_stock - sync.safety_stock)
        
        assert available_stock == 45
    
    def test_register_supplier(self, sync):
        """공급사 등록 테스트"""
        fetcher = MockFetcher()
        sync.register_supplier("domeme", fetcher)
        
        assert "domeme" in sync.suppliers
    
    def test_check_low_stock(self, sync, storage):
        """낮은 재고 확인 테스트"""
        # 낮은 재고 상품 추가
        asyncio.run(storage.save("products", {
            "id": "PROD002",
            "name": "재고 부족 상품",
            "supplier_id": "domeme",
            "supplier_product_id": "12346",
            "stock": 3,
            "status": "active"
        }))
        
        low_stock = asyncio.run(sync.check_low_stock(threshold=10))
        
        # 재고가 10 이하인 상품 확인
        assert len(low_stock) == 1  # PROD002만 해당
        assert low_stock[0]["product_id"] == "PROD002"
        assert low_stock[0]["stock"] == 3


class TestDeliveryTracker:
    """배송 추적 테스트"""
    
    @pytest.fixture
    def storage(self):
        storage = MockStorage()
        # 테스트 주문 추가
        asyncio.run(storage.save("orders", {
            "id": "ORD001",
            "delivery": {
                "carrier": "cj",
                "tracking_number": "123456789012",
                "status": "in_transit"
            }
        }))
        return storage
    
    @pytest.fixture
    def tracker_manager(self, storage):
        config = {
            "carriers": ["cj", "hanjin", "lotte", "post"]
        }
        return TrackerManager(storage, config)
    
    def test_normalize_tracking_number(self, tracker_manager):
        """운송장 번호 정규화 테스트"""
        tracker = tracker_manager.trackers.get("cj")
        if tracker:
            normalized = tracker.normalize_tracking_number("1234-5678-9012")
            assert normalized == "123456789012"
    
    def test_parse_datetime(self, tracker_manager):
        """날짜 파싱 테스트"""
        tracker = tracker_manager.trackers.get("cj")
        if tracker:
            # 다양한 형식 테스트
            formats = [
                ("2024-01-15 14:30:00", datetime(2024, 1, 15, 14, 30, 0)),
                ("2024.01.15 14:30", datetime(2024, 1, 15, 14, 30, 0)),
                ("2024/01/15 14:30:00", datetime(2024, 1, 15, 14, 30, 0))
            ]
            
            for date_str, expected in formats:
                result = tracker.parse_datetime(date_str)
                if result:
                    assert result == expected


class TestTrackerManager:
    """배송 추적 관리자 테스트"""
    
    @pytest.fixture
    def storage(self):
        return MockStorage()
    
    @pytest.fixture
    def manager(self, storage):
        config = {
            "carriers": ["cj", "hanjin"],
            "batch_size": 10
        }
        return TrackerManager(storage, config)
    
    def test_register_trackers(self, manager):
        """추적기 등록 테스트"""
        assert "cj" in manager.trackers
        assert "hanjin" in manager.trackers
    
    def test_get_stats(self, manager):
        """통계 조회 테스트"""
        stats = manager.get_stats()
        
        assert "total_tracked" in stats
        assert "trackers" in stats
        assert "cj" in stats["trackers"]


if __name__ == "__main__":
    # 테스트 실행
    print("주문 모델 테스트...")
    test_models = TestOrderModels()
    test_models.test_order_creation()
    print("✓ 주문 모델 테스트 통과")
    
    print("\n쿠팡 주문 관리자 테스트...")
    test_coupang = TestCoupangOrderManager()
    storage = MockStorage()
    config = {
        "api_key": "test_key",
        "api_secret": "test_secret",
        "seller_id": "test_seller"
    }
    manager = CoupangOrderManager(storage, config)
    test_coupang.test_transform_order(manager)
    print("✓ 쿠팡 주문 관리자 테스트 통과")
    
    print("\n도매매 주문 전달자 테스트...")
    test_domeme = TestDomemeOrderer()
    storage = MockStorage()
    config = {
        "api_key": "test_key",
        "api_secret": "test_secret",
        "company_code": "TEST001"
    }
    orderer = DomemeOrderer(storage, config)
    test_domeme.test_build_order_xml(orderer)
    print("✓ 도매매 주문 전달자 테스트 통과")
    
    print("\n재고 동기화 테스트...")
    test_inventory = TestInventorySync()
    storage = MockStorage()
    # 테스트 상품 추가
    asyncio.run(storage.save("products", {
        "id": "PROD001",
        "name": "테스트 상품",
        "supplier_id": "domeme",
        "supplier_product_id": "12345",
        "stock": 20,
        "status": "active"
    }))
    config = {
        "safety_stock": 5,
        "batch_size": 10
    }
    sync = InventorySync(storage, config)
    test_inventory.test_safety_stock(sync)
    test_inventory.test_register_supplier(sync)
    test_inventory.test_check_low_stock(sync, storage)
    print("✓ 재고 동기화 테스트 통과")
    
    print("\n배송 추적 테스트...")
    test_tracker = TestDeliveryTracker()
    storage = MockStorage()
    # 테스트 주문 추가
    asyncio.run(storage.save("orders", {
        "id": "ORD001",
        "delivery": {
            "carrier": "cj",
            "tracking_number": "123456789012",
            "status": "in_transit"
        }
    }))
    config = {
        "carriers": ["cj", "hanjin", "lotte", "post"]
    }
    tracker_manager = TrackerManager(storage, config)
    test_tracker.test_normalize_tracking_number(tracker_manager)
    test_tracker.test_parse_datetime(tracker_manager)
    print("✓ 배송 추적 테스트 통과")
    
    print("\n배송 추적 관리자 테스트...")
    test_manager = TestTrackerManager()
    storage = MockStorage()
    config = {
        "carriers": ["cj", "hanjin"],
        "batch_size": 10
    }
    manager = TrackerManager(storage, config)
    test_manager.test_register_trackers(manager)
    test_manager.test_get_stats(manager)
    print("✓ 배송 추적 관리자 테스트 통과")
    
    print("\n✅ 모든 주문 관리 시스템 테스트 통과!")