"""
주문 관리 시스템 통합 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import pytest

from dropshipping.models.order import Order, OrderStatus, DeliveryStatus
from dropshipping.orders.coupang import CoupangOrderManager
from dropshipping.orders.supplier.domeme_orderer import DomemeOrderer
from dropshipping.orders.inventory.inventory_sync import InventorySync
from dropshipping.orders.delivery.tracker_manager import TrackerManager
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
                        # 복잡한 필터 처리
                        if "$nin" in value:
                            if item.get(key) in value["$nin"]:
                                match = False
                                break
                        if "$in" in value:
                            if item.get(key) not in value["$in"]:
                                match = False
                                break
                        if "$lte" in value:
                            if item.get(key, 0) > value["$lte"]:
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
        
        # 중첩된 키 처리 (예: "delivery.status")
        for key, value in data.items():
            if "." in key:
                parts = key.split(".")
                current = self.data[table][id]
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            else:
                self.data[table][id][key] = value
        
        self.data[table][id]["updated_at"] = datetime.now()
        return self.data[table][id]
    
    async def delete(self, table: str, id: str) -> bool:
        if table not in self.data or id not in self.data[table]:
            return False
        
        del self.data[table][id]
        return True


class TestOrderWorkflow:
    """주문 워크플로우 통합 테스트"""
    
    @pytest.fixture
    def storage(self):
        return MockStorage()
    
    @pytest.fixture
    def coupang_manager(self, storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "vendor_id": "test_vendor",
            "test_mode": True
        }
        return CoupangOrderManager(storage, config)
    
    @pytest.fixture
    def domeme_orderer(self, storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "company_code": "TEST001"
        }
        return DomemeOrderer(storage, config)
    
    @pytest.fixture
    def inventory_sync(self, storage):
        return InventorySync(storage)
    
    @pytest.fixture
    def tracker_manager(self, storage):
        config = {
            "carriers": ["cj", "hanjin", "lotte", "post"]
        }
        return TrackerManager(storage, config)
    
    @patch('httpx.AsyncClient.get')
    @patch('httpx.AsyncClient.post')
    def test_complete_order_workflow(
        self,
        mock_post,
        mock_get,
        storage,
        coupang_manager,
        domeme_orderer,
        inventory_sync,
        tracker_manager
    ):
        """전체 주문 워크플로우 테스트"""
        
        # 1. 테스트 상품 데이터 준비
        product_data = {
            "id": "PROD001",
            "name": "테스트 상품",
            "supplier_id": "domeme",
            "supplier_product_id": "DM12345",
            "stock": 100,
            "status": "active",
            "marketplace_listings": {
                "coupang": {
                    "marketplace_product_id": "CP12345",
                    "stock": 100
                }
            }
        }
        asyncio.run(storage.create("products", product_data))
        
        # 2. 쿠팡에서 주문 수집
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "code": "SUCCESS",
            "data": [{
                "orderId": "123456",
                "orderedAt": "2024-01-01T10:00:00Z",
                "orderItems": [{
                    "sellerProductId": "PROD001",
                    "productId": 12345,
                    "sellerProductName": "테스트 상품",
                    "vendorItemId": "DM12345",
                    "orderPrice": 10000,
                    "shippingCount": 2,
                    "status": "ACCEPT"
                }],
                "ordererName": "홍길동",
                "ordererPhoneNumber": "010-1234-5678",
                "receiverName": "홍길동",
                "receiverPhoneNumber1": "010-1234-5678",
                "receiverPostCode": "12345",
                "receiverAddr1": "서울시 강남구",
                "receiverAddr2": "테스트동 123",
                "totalPaidAmount": 22500,
                "shippingPrice": 2500
            }]
        }
        mock_get.return_value = mock_get_response
        
        orders = asyncio.run(coupang_manager.process_new_orders())
        assert len(orders) == 1
        order = orders[0]
        
        # 3. 도매매에 주문 전달
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <code>00</code>
            <message>주문 성공</message>
            <orderNo>DM202401010001</orderNo>
        </response>"""
        mock_post.return_value = mock_post_response
        
        success = asyncio.run(domeme_orderer.process_order("1"))
        assert success is True
        
        # 주문 정보 확인
        updated_order = asyncio.run(storage.get("orders", "1"))
        assert updated_order["supplier_order_id"] == "DM202401010001"
        
        # 4. 재고 동기화
        # 재고 감소 시뮬레이션
        asyncio.run(storage.update("products", "PROD001", {"stock": 98}))
        
        # 재고 동기화 실행
        inventory_sync.register_supplier("domeme", Mock())
        inventory_sync.register_marketplace("coupang", Mock())
        
        sync_success = asyncio.run(inventory_sync.sync_product("PROD001"))
        assert sync_success is True
        
        # 5. 배송 정보 업데이트
        # 도매매에서 배송 시작
        mock_post_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <code>00</code>
            <orderStatus>04</orderStatus>
            <orderStatusName>배송중</orderStatusName>
            <tracking>
                <carrier>CJ대한통운</carrier>
                <trackingNo>1234567890</trackingNo>
            </tracking>
        </response>"""
        
        asyncio.run(domeme_orderer.sync_order_status("1", "DM202401010001"))
        
        # 쿠팡에 배송 정보 전달
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"code": "SUCCESS"}
        
        tracking_success = asyncio.run(
            coupang_manager.update_tracking_info("123456", "CJ대한통운", "1234567890")
        )
        assert tracking_success is True
        
        # 6. 배송 추적
        with patch.object(tracker_manager.trackers.get("cj", Mock()), 'track') as mock_track:
            mock_track.return_value = {
                "status": "delivered",
                "delivered_at": datetime.now(),
                "history": [
                    {"status": "picked_up", "timestamp": datetime.now() - timedelta(days=2)},
                    {"status": "in_transit", "timestamp": datetime.now() - timedelta(days=1)},
                    {"status": "delivered", "timestamp": datetime.now()}
                ]
            }
            
            tracking_info = asyncio.run(
                tracker_manager.track("cj", "1234567890")
            )
            assert tracking_info["status"] == "delivered"
        
        # 7. 주문 상태 최종 업데이트
        asyncio.run(storage.update(
            "orders",
            "1",
            {
                "status": OrderStatus.DELIVERED.value,
                "delivery.status": DeliveryStatus.DELIVERED.value,
                "delivery.delivered_at": datetime.now()
            }
        ))
        
        # 최종 주문 상태 확인
        final_order = asyncio.run(storage.get("orders", "1"))
        assert final_order["status"] == OrderStatus.DELIVERED.value
        assert final_order["delivery"]["status"] == DeliveryStatus.DELIVERED.value
    
    def test_inventory_sync_low_stock_alert(self, storage, inventory_sync):
        """낮은 재고 알림 테스트"""
        
        # 낮은 재고 상품 생성
        products = [
            {
                "id": f"PROD{i:03d}",
                "name": f"테스트 상품 {i}",
                "supplier_id": "domeme",
                "stock": i * 5,  # 0, 5, 10, 15...
                "status": "active"
            }
            for i in range(5)
        ]
        
        for product in products:
            asyncio.run(storage.create("products", product))
        
        # 재고 10개 이하 상품 확인
        low_stock = asyncio.run(inventory_sync.check_low_stock(threshold=10))
        
        assert len(low_stock) == 3  # 0, 5, 10
        assert all(p["stock"] <= 10 for p in low_stock)
    
    def test_batch_order_processing(self, storage, domeme_orderer):
        """배치 주문 처리 테스트"""
        
        # 여러 주문 생성
        order_ids = []
        for i in range(5):
            order_data = {
                "marketplace": "coupang",
                "marketplace_order_id": f"CP{i:05d}",
                "status": OrderStatus.CONFIRMED.value,
                "items": [{
                    "id": f"ITEM{i}",
                    "supplier_product_id": f"DM{i:05d}",
                    "product_name": f"상품 {i}",
                    "quantity": 1,
                    "unit_price": 10000
                }],
                "customer": {
                    "name": "테스트 고객",
                    "phone": "010-0000-0000",
                    "recipient_name": "테스트 고객",
                    "recipient_phone": "010-0000-0000",
                    "postal_code": "12345",
                    "address": "테스트 주소"
                },
                "payment": {
                    "method": "card",
                    "status": "completed",
                    "total_amount": 10000,
                    "product_amount": 10000,
                    "shipping_fee": 0
                },
                "delivery": {
                    "status": "pending"
                }
            }
            
            created = asyncio.run(storage.create("orders", order_data))
            order_ids.append(created["id"])
        
        # Mock 응답 설정
        with patch.object(domeme_orderer, 'place_order') as mock_place:
            mock_place.return_value = (True, {"order_id": "DM123456"})
            
            # 배치 처리
            results = asyncio.run(domeme_orderer.process_batch_orders(order_ids))
            
            assert len(results) == 5
            assert all(results.values())  # 모두 성공
            assert mock_place.call_count == 5
    
    def test_order_tracking_update_all(self, storage, tracker_manager):
        """전체 배송 추적 업데이트 테스트"""
        
        # 배송중 주문 생성
        for i in range(3):
            order_data = {
                "id": str(i + 1),
                "marketplace": "coupang",
                "status": OrderStatus.SHIPPED.value,
                "delivery": {
                    "status": DeliveryStatus.IN_TRANSIT.value,
                    "carrier": ["cj", "hanjin", "lotte"][i],
                    "tracking_number": f"123456789{i}"
                }
            }
            asyncio.run(storage.create("orders", order_data))
        
        # Mock 설정
        for tracker_name in ["cj", "hanjin", "lotte"]:
            if tracker_name in tracker_manager.trackers:
                tracker = tracker_manager.trackers[tracker_name]
                tracker.update_all_pending_orders = AsyncMock(return_value={
                    "total": 1,
                    "updated": 1,
                    "delivered": 1,
                    "failed": 0
                })
        
        # 전체 업데이트 실행
        results = asyncio.run(tracker_manager.update_all_pending_orders())
        
        assert results["total_orders"] == 3
        assert results["updated"] == 3
        assert results["delivered"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])