"""
주문 관리 시스템 통합 테스트
전체 주문 워크플로우 검증
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from dropshipping.orders.coupang import CoupangOrderManager
from dropshipping.orders.supplier.domeme_orderer import DomemeOrderer
from dropshipping.orders.inventory.inventory_sync import InventorySync
from dropshipping.orders.delivery.tracker_manager import TrackerManager


class TestOrderWorkflow:
    """주문 워크플로우 통합 테스트"""
    
    @pytest.fixture
    def coupang_manager(self, mock_storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "vendor_id": "test_vendor",
            "test_mode": True
        }
        return CoupangOrderManager(mock_storage, config)
    
    @pytest.fixture
    def domeme_orderer(self, mock_storage):
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "company_code": "TEST001"
        }
        return DomemeOrderer(mock_storage, config)
    
    @pytest.fixture
    def inventory_sync(self, mock_storage):
        config = {
            "sync_interval": 60,
            "low_stock_threshold": 10
        }
        return InventorySync(mock_storage, config)
    
    @pytest.fixture
    def tracker_manager(self, mock_storage):
        return TrackerManager(mock_storage)
    
    @pytest.mark.asyncio
    async def test_complete_order_workflow(
        self,
        mock_storage,
        coupang_manager,
        domeme_orderer,
        inventory_sync,
        tracker_manager
    ):
        """전체 주문 워크플로우 테스트"""
        
        # 1. 상품 및 재고 정보 준비
        await mock_storage.create("products", {
            "id": "P001",
            "name": "테스트 상품",
            "supplier_product_id": "SP001",
            "marketplace_product_id": "MP001",
            "supplier": "domeme",
            "marketplace": "coupang",
            "price": 10000,
            "cost": 7000
        })
        
        await mock_storage.create("inventory", {
            "product_id": "P001",
            "supplier_stock": 100,
            "marketplace_stock": 100,
            "reserved_stock": 0,
            "available_stock": 100
        })
        
        # 2. 주문 수집 (쿠팡에서)
        with patch.object(coupang_manager, 'fetch_orders') as mock_fetch:
            mock_fetch.return_value = [{
                "orderId": "CP001",
                "orderItems": [{
                    "vendorItemId": "MP001",
                    "vendorItemName": "테스트 상품",
                    "shippingCount": 2,
                    "salesPrice": 10000,
                    "orderPrice": 20000
                }],
                "orderer": {
                    "name": "홍길동",
                    "phone": "010-1234-5678",
                    "email": "test@example.com"
                },
                "receiver": {
                    "name": "홍길동",
                    "phone": "010-1234-5678",
                    "addr1": "서울시 강남구",
                    "addr2": "테스트동 123",
                    "postCode": "12345"
                },
                "paymentDate": datetime.now().isoformat()
            }]
            
            collected = await coupang_manager.collect_orders()
            assert collected == 1
        
        # 주문 확인
        orders = await mock_storage.list("orders", {"marketplace": "coupang"})
        assert len(orders) == 1
        order = orders[0]
        assert order["order_number"] == "CP001"
        assert order["total_amount"] == 20000
        assert order["status"] == "pending"
        
        # 3. 재고 예약
        await inventory_sync.reserve_stock("P001", 2)
        
        inventory = await mock_storage.get("inventory", filters={"product_id": "P001"})
        assert inventory["reserved_stock"] == 2
        assert inventory["available_stock"] == 98
        
        # 4. 공급사 주문 전달
        with patch.object(domeme_orderer, '_send_order_to_api') as mock_send:
            mock_send.return_value = {
                "success": True,
                "orderNo": "DM001",
                "message": "주문 성공"
            }
            
            result = await domeme_orderer.place_order(order["id"])
            assert result["success"] == True
        
        # 주문 상태 확인
        updated_order = await mock_storage.get("orders", id=order["id"])
        assert updated_order["supplier_order_number"] == "DM001"
        assert updated_order["status"] == "confirmed"
        
        # 5. 배송 시작 및 추적
        # 배송 정보 업데이트
        await mock_storage.update("orders", order["id"], {
            "delivery.company": "CJ대한통운",
            "delivery.tracking_number": "1234567890",
            "delivery.status": "shipping",
            "status": "shipping"
        })
        
        # 배송 추적
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "배송중",
                "location": "서울 강남 물류센터",
                "time": datetime.now().isoformat()
            }
            mock_get.return_value = mock_response
            
            tracking_info = await tracker_manager.track_delivery(
                "CJ대한통운",
                "1234567890"
            )
            assert tracking_info["status"] == "배송중"
        
        # 6. 재고 차감
        await inventory_sync.confirm_stock("P001", 2)
        
        final_inventory = await mock_storage.get("inventory", filters={"product_id": "P001"})
        assert final_inventory["supplier_stock"] == 98
        assert final_inventory["marketplace_stock"] == 98
        assert final_inventory["reserved_stock"] == 0
        
        # 7. 주문 완료
        await mock_storage.update("orders", order["id"], {
            "status": "completed",
            "completed_at": datetime.now()
        })
        
        completed_order = await mock_storage.get("orders", id=order["id"])
        assert completed_order["status"] == "completed"
        assert completed_order["completed_at"] is not None
    
    @pytest.mark.asyncio
    async def test_order_cancellation_workflow(
        self,
        mock_storage,
        coupang_manager,
        inventory_sync
    ):
        """주문 취소 워크플로우 테스트"""
        
        # 기존 주문 생성
        order = await mock_storage.create("orders", {
            "order_number": "CP002",
            "marketplace": "coupang",
            "supplier": "domeme",
            "status": "confirmed",
            "items": [{
                "product_id": "P001",
                "quantity": 1,
                "price": 10000
            }],
            "total_amount": 10000
        })
        
        # 재고 예약 상태
        await mock_storage.create("inventory", {
            "product_id": "P001",
            "supplier_stock": 100,
            "marketplace_stock": 100,
            "reserved_stock": 1,
            "available_stock": 99
        })
        
        # 주문 취소
        with patch.object(coupang_manager, '_cancel_order_api') as mock_cancel:
            mock_cancel.return_value = {"success": True}
            
            result = await coupang_manager.cancel_order(order["id"])
            assert result["success"] == True
        
        # 재고 복원
        await inventory_sync.release_stock("P001", 1)
        
        # 상태 확인
        cancelled_order = await mock_storage.get("orders", id=order["id"])
        assert cancelled_order["status"] == "cancelled"
        
        inventory = await mock_storage.get("inventory", filters={"product_id": "P001"})
        assert inventory["reserved_stock"] == 0
        assert inventory["available_stock"] == 100
    
    @pytest.mark.asyncio
    async def test_low_stock_alert(self, mock_storage, inventory_sync):
        """낮은 재고 알림 테스트"""
        
        # 낮은 재고 상품
        await mock_storage.create("products", {
            "id": "P002",
            "name": "재고 부족 상품",
            "supplier": "domeme"
        })
        
        await mock_storage.create("inventory", {
            "product_id": "P002",
            "supplier_stock": 5,
            "marketplace_stock": 5,
            "reserved_stock": 0,
            "available_stock": 5
        })
        
        # 재고 체크
        low_stock_items = await inventory_sync.check_low_stock()
        assert len(low_stock_items) == 1
        assert low_stock_items[0]["product_id"] == "P002"
        assert low_stock_items[0]["available_stock"] == 5
    
    @pytest.mark.asyncio
    async def test_bulk_order_processing(
        self,
        mock_storage,
        domeme_orderer
    ):
        """대량 주문 처리 테스트"""
        
        # 여러 주문 생성
        orders = []
        for i in range(5):
            order = await mock_storage.create("orders", {
                "order_number": f"CP00{i+3}",
                "marketplace": "coupang",
                "supplier": "domeme",
                "status": "pending",
                "items": [{
                    "product_id": f"P00{i+1}",
                    "quantity": 1,
                    "price": 10000
                }],
                "total_amount": 10000
            })
            orders.append(order)
        
        # 배치 주문 처리
        with patch.object(domeme_orderer, '_send_order_to_api') as mock_send:
            mock_send.return_value = {
                "success": True,
                "orderNo": "DM002",
                "message": "주문 성공"
            }
            
            results = await domeme_orderer.place_bulk_orders([o["id"] for o in orders])
            assert len(results) == 5
            assert all(r["success"] for r in results)
        
        # 모든 주문 상태 확인
        confirmed_orders = await mock_storage.list("orders", {"status": "confirmed"})
        assert len(confirmed_orders) == 5