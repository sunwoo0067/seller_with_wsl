from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from dropshipping.models.product import ProductStatus, StandardProduct
from dropshipping.sourcing.self_sales.sync_sales import SalesSynchronizer
from dropshipping.storage.base import BaseStorage


@pytest.fixture
def mock_storage():
    """Mock BaseStorage 인스턴스"""
    storage = MagicMock()  # spec=BaseStorage 제거하여 유연성 확보

    # Mock get_processed_product
    def get_processed_product_side_effect(product_id):
        if product_id == "prod1":
            return StandardProduct(
                id="prod1",
                supplier_id="sup1",
                supplier_product_id="sp1",
                name="Product 1",
                cost=Decimal("100"),
                price=Decimal("150"),
                stock=10,
                status=ProductStatus.ACTIVE,
            )
        elif product_id == "prod2":
            return StandardProduct(
                id="prod2",
                supplier_id="sup2",
                supplier_product_id="sp2",
                name="Product 2",
                cost=Decimal("200"),
                price=Decimal("250"),
                stock=5,
                status=ProductStatus.ACTIVE,
            )
        return None

    storage.get_processed_product = MagicMock(side_effect=get_processed_product_side_effect)

    # Mock list 메서드 (sync_sales_data에서 사용)
    storage.list = AsyncMock(
        return_value=[
            {
                "order_date": datetime.now() - timedelta(days=5),
                "marketplace_id": "mp1",
                "account_id": "acc1",
                "items": [{"product_id": "prod1", "quantity": 2, "total_amount": Decimal("300")}],
            },
            {
                "order_date": datetime.now() - timedelta(days=3),
                "marketplace_id": "mp1",
                "account_id": "acc1",
                "items": [
                    {"product_id": "prod1", "quantity": 1, "total_amount": Decimal("150")},
                    {"product_id": "prod2", "quantity": 1, "total_amount": Decimal("250")},
                ],
            },
        ]
    )
    
    # Mock get_sales_data도 유지 (다른 테스트에서 사용할 수 있음)
    storage.get_sales_data = storage.list

    # Mock upsert
    storage.upsert = AsyncMock(return_value=[])

    return storage


@pytest.fixture
def sales_synchronizer(mock_storage):
    """SalesSynchronizer 인스턴스"""
    return SalesSynchronizer(storage=mock_storage)


@pytest.mark.asyncio
async def test_sync_sales_data_success(sales_synchronizer, mock_storage):
    """판매 데이터 동기화 성공 테스트"""
    await sales_synchronizer.sync_sales_data(lookback_days=7)

    # storage.list가 올바른 인수로 호출되었는지 확인
    mock_storage.list.assert_called_once()
    args, kwargs = mock_storage.list.call_args
    assert args[0] == "orders"  # table name
    assert "filters" in kwargs  # filters should be provided

    # storage.upsert가 올바른 인수로 호출되었는지 확인
    mock_storage.upsert.assert_called_once()
    args, kwargs = mock_storage.upsert.call_args
    assert args[0] == "sales_products"
    assert len(args[1]) == 2  # prod1, prod2 두 개의 상품이 집계되어야 함
    assert kwargs["on_conflict"] == "product_id,marketplace_id,account_id"

    # 집계된 데이터 내용 확인
    sales_records = args[1]
    prod1_record = next(r for r in sales_records if r["product_id"] == "prod1")
    prod2_record = next(r for r in sales_records if r["product_id"] == "prod2")

    assert prod1_record["total_sales_quantity"] == 3
    assert prod1_record["total_sales_revenue"] == 450.0  # Decimal이 float으로 변환됨
    assert prod2_record["total_sales_quantity"] == 1
    assert prod2_record["total_sales_revenue"] == 250.0


@pytest.mark.asyncio
async def test_sync_sales_data_no_orders(sales_synchronizer, mock_storage):
    """주문 데이터가 없는 경우 동기화 테스트"""
    mock_storage.list.return_value = []

    await sales_synchronizer.sync_sales_data(lookback_days=7)

    # storage.upsert가 호출되지 않았는지 확인
    mock_storage.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_sync_sales_data_product_not_found(sales_synchronizer, mock_storage):
    """상품 정보를 찾을 수 없는 경우 테스트"""
    # get_processed_product가 None을 반환하도록 설정
    mock_storage.get_processed_product.return_value = None

    # 주문 데이터는 있지만 상품 정보가 없는 경우
    mock_storage.list.return_value = [
        {
            "order_date": datetime.now() - timedelta(days=1),
            "marketplace_id": "mp1",
            "account_id": "acc1",
            "items": [
                {"product_id": "unknown_prod", "quantity": 1, "total_amount": Decimal("100")}
            ],
        }
    ]

    await sales_synchronizer.sync_sales_data(lookback_days=7)

    # upsert가 호출되지 않았는지 확인 (집계된 판매 기록이 없으므로)
    mock_storage.upsert.assert_not_called()
