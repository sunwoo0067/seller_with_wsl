"""
주문 통합 프로세서 테스트
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dropshipping.models.order import (
    CustomerInfo,
    DeliveryInfo,
    Order,
    OrderItem,
    OrderStatus,
    PaymentInfo,
)
from dropshipping.orders.order_processor import OrderProcessor


class MockStorage:
    """테스트용 Mock Storage"""

    def __init__(self):
        self.orders = {}
        self.products = {
            "P001": {"id": "P001", "supplier_id": "domeme", "name": "테스트 상품 1"},
            "P002": {"id": "P002", "supplier_id": "domeme", "name": "테스트 상품 2"},
        }
        self.order_id_counter = 1

    async def save_order(self, order: Order) -> Order:
        """주문 저장"""
        order.id = f"ORDER_{self.order_id_counter}"
        self.order_id_counter += 1
        self.orders[order.id] = order
        return order

    async def update_order(self, order: Order) -> Order:
        """주문 업데이트"""
        if order.id in self.orders:
            self.orders[order.id] = order
        return order

    async def get_product(self, product_id: str):
        """상품 조회"""
        return self.products.get(product_id)

    async def get_active_orders(self):
        """진행중인 주문 조회"""
        return [
            order
            for order in self.orders.values()
            if order.status in [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.SHIPPED]
        ]

    async def get_orders_for_tracking(self):
        """배송 추적 대상 주문 조회"""
        return [
            order
            for order in self.orders.values()
            if order.status in [OrderStatus.PREPARING, OrderStatus.SHIPPED]
            and not order.delivery.tracking_number
        ]

    async def get_cancelled_orders(self):
        """취소 요청된 주문 조회"""
        return [order for order in self.orders.values() if order.status == OrderStatus.CANCELLED]


@pytest.fixture
def mock_storage():
    """Mock Storage 픽스처"""
    return MockStorage()


@pytest.fixture
def sample_order():
    """샘플 주문 데이터"""
    return Order(
        id="TEST_ORDER_1",
        marketplace="coupang",
        marketplace_order_id="CP123456",
        order_date=datetime.now(),
        status=OrderStatus.CONFIRMED,
        items=[
            OrderItem(
                id="ITEM1",
                product_id="P001",
                marketplace_product_id="MP001",
                supplier_product_id="SP001",
                product_name="테스트 상품 1",
                quantity=2,
                unit_price=10000,
                total_price=20000,
            )
        ],
        customer=CustomerInfo(
            name="홍길동",
            phone="010-1234-5678",
            recipient_name="홍길동",
            recipient_phone="010-1234-5678",
            postal_code="12345",
            address="서울시 강남구",
            address_detail="테스트동 123",
        ),
        payment=PaymentInfo(
            method="card",
            status="completed",
            total_amount=22500,
            product_amount=20000,
            shipping_fee=2500,
        ),
        delivery=DeliveryInfo(
            method="택배",
            status="pending",
        ),
    )


@pytest.fixture
def order_processor_config():
    """주문 프로세서 설정"""
    return {
        "coupang": {
            "enabled": True,
            "api_key": "test_key",
            "api_secret": "test_secret",
            "vendor_id": "test_vendor",
        },
        "domeme": {
            "enabled": True,
            "api_key": "test_key",
        },
    }


class TestOrderProcessor:
    """주문 프로세서 테스트"""

    @pytest.mark.asyncio
    async def test_process_new_orders(self, mock_storage, sample_order, order_processor_config):
        """신규 주문 처리 테스트"""
        processor = OrderProcessor(mock_storage, order_processor_config)

        # Mock 설정
        mock_coupang_manager = Mock()
        mock_coupang_manager.fetch_orders = AsyncMock(return_value=[{"orderId": "CP123456"}])
        mock_coupang_manager.transform_order = AsyncMock(return_value=sample_order)
        processor.order_managers["coupang"] = mock_coupang_manager

        mock_domeme_orderer = Mock()
        mock_domeme_orderer.place_order = AsyncMock(return_value="DOMEME_ORDER_001")
        processor.supplier_orderers["domeme"] = mock_domeme_orderer

        # 실행
        results = await processor.process_new_orders()

        # 검증
        assert results["coupang"] == 1
        assert len(mock_storage.orders) == 1

        saved_order = list(mock_storage.orders.values())[0]
        assert saved_order.supplier_order_id == "DOMEME_ORDER_001"
        assert saved_order.supplier_ordered_at is not None

    @pytest.mark.asyncio
    async def test_group_orders_by_supplier(self, mock_storage, sample_order):
        """공급사별 주문 그룹화 테스트"""
        processor = OrderProcessor(mock_storage, {})

        # 다른 공급사 상품 추가
        mock_storage.products["P003"] = {
            "id": "P003",
            "supplier_id": "ownerclan",
            "name": "테스트 상품 3",
        }

        # 주문 2개 생성
        order1 = sample_order
        order2 = Order(
            id="TEST_ORDER_2",
            marketplace="coupang",
            marketplace_order_id="CP123457",
            order_date=datetime.now(),
            status=OrderStatus.CONFIRMED,
            items=[
                OrderItem(
                    id="ITEM2",
                    product_id="P003",
                    marketplace_product_id="MP003",
                    supplier_product_id="SP003",
                    product_name="테스트 상품 3",
                    quantity=1,
                    unit_price=15000,
                    total_price=15000,
                )
            ],
            customer=sample_order.customer,
            payment=sample_order.payment,
            delivery=sample_order.delivery,
        )

        # 실행
        grouped = await processor._group_orders_by_supplier([order1, order2])

        # 검증
        assert len(grouped) == 2
        assert "domeme" in grouped
        assert "ownerclan" in grouped
        assert len(grouped["domeme"]) == 1
        assert len(grouped["ownerclan"]) == 1

    @pytest.mark.asyncio
    async def test_sync_order_status(self, mock_storage, sample_order):
        """주문 상태 동기화 테스트"""
        # 주문 저장
        await mock_storage.save_order(sample_order)

        processor = OrderProcessor(mock_storage, {"coupang": {"enabled": True}})

        # Mock 설정
        mock_coupang_manager = Mock()
        mock_coupang_manager.fetch_order_detail = AsyncMock(
            return_value={"orderId": "CP123456", "status": "SHIPPED"}
        )

        updated_order = sample_order.model_copy()
        updated_order.status = OrderStatus.SHIPPED
        mock_coupang_manager.transform_order = AsyncMock(return_value=updated_order)

        processor.order_managers["coupang"] = mock_coupang_manager

        # 실행
        results = await processor.sync_order_status()

        # 검증
        assert results["updated"] == 1
        assert results["failed"] == 0

        updated = mock_storage.orders[sample_order.id]
        assert updated.status == OrderStatus.SHIPPED

    @pytest.mark.asyncio
    async def test_update_tracking_info(self, mock_storage, sample_order):
        """배송 정보 업데이트 테스트"""
        # 주문 상태를 배송준비중으로 변경
        sample_order.status = OrderStatus.PREPARING
        sample_order.supplier_order_id = "DOMEME_ORDER_001"
        await mock_storage.save_order(sample_order)

        processor = OrderProcessor(
            mock_storage, {"coupang": {"enabled": True}, "domeme": {"enabled": True}}
        )

        # Mock 설정
        mock_domeme_orderer = Mock()
        mock_domeme_orderer.get_tracking_info = AsyncMock(
            return_value={"carrier": "CJ대한통운", "tracking_number": "1234567890"}
        )
        processor.supplier_orderers["domeme"] = mock_domeme_orderer

        mock_coupang_manager = Mock()
        mock_coupang_manager.update_tracking_info = AsyncMock(return_value=True)
        processor.order_managers["coupang"] = mock_coupang_manager

        # 실행
        results = await processor.update_tracking_info()

        # 검증
        assert results["updated"] == 1
        assert results["failed"] == 0

        updated = mock_storage.orders[sample_order.id]
        assert updated.delivery.carrier == "CJ대한통운"
        assert updated.delivery.tracking_number == "1234567890"

    @pytest.mark.asyncio
    async def test_process_cancellations(self, mock_storage, sample_order):
        """취소 처리 테스트"""
        # 주문 상태를 취소로 변경
        sample_order.status = OrderStatus.CANCELLED
        sample_order.supplier_order_id = "DOMEME_ORDER_001"
        await mock_storage.save_order(sample_order)

        processor = OrderProcessor(mock_storage, {"domeme": {"enabled": True}})

        # Mock 설정
        mock_domeme_orderer = Mock()
        mock_domeme_orderer.cancel_order = AsyncMock(return_value=True)
        processor.supplier_orderers["domeme"] = mock_domeme_orderer

        # 실행
        results = await processor.process_cancellations()

        # 검증
        assert results["processed"] == 1
        assert results["failed"] == 0

        updated = mock_storage.orders[sample_order.id]
        assert updated.supplier_order_status == "cancelled"
