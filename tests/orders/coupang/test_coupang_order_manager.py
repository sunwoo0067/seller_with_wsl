import asyncio
from datetime import datetime
from decimal import Decimal

import pytest
import respx
from httpx import Response

from dropshipping.models.order import OrderStatus
from dropshipping.orders.coupang.coupang_order_manager import CoupangOrderManager


@pytest.fixture
def coupang_config():
    return {
        "vendor_id": "test_vendor",
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
        "test_mode": True,
    }


@pytest.fixture
def mock_storage():
    class MockStorage:
        async def get(self, key):
            return None

        async def set(self, key, value):
            pass

    return MockStorage()


@pytest.fixture
def manager(mock_storage, coupang_config):
    return CoupangOrderManager(storage=mock_storage, config=coupang_config)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orders(manager: CoupangOrderManager):
    # Given: Mock a successful API response with pagination
    base_url = manager.base_url
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{manager.vendor_id}/ordersheets"

    mock_response_page1 = {
        "code": "SUCCESS",
        "message": "OK",
        "data": [{"orderId": 101}, {"orderId": 102}],
        "nextToken": "token123",
    }
    mock_response_page2 = {
        "code": "SUCCESS",
        "message": "OK",
        "data": [{"orderId": 103}],
        "nextToken": None,
    }

    respx.get(url__regex=f"{base_url}{path}.*").mock(
        side_effect=[
            Response(200, json=mock_response_page1),
            Response(200, json=mock_response_page2),
        ]
    )

    # When: Fetching orders
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 15)
    orders = await manager.fetch_orders(start_date=start_date, end_date=end_date)

    # Then: All orders from both pages should be returned
    assert len(orders) == 3
    assert orders[0]["orderId"] == 101
    assert orders[2]["orderId"] == 103


@pytest.mark.asyncio
@respx.mock
async def test_fetch_order_detail(manager: CoupangOrderManager):
    # Given: Mock a successful API response for a single order
    order_id = "12345"
    base_url = manager.base_url
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{manager.vendor_id}/ordersheets/{order_id}"
    mock_response = {"code": "SUCCESS", "data": {"orderId": order_id, "ordererName": "Test User"}}
    respx.get(f"{base_url}{path}").mock(return_value=Response(200, json=mock_response))

    # When: Fetching order detail
    order_detail = await manager.fetch_order_detail(order_id)

    # Then: The correct order detail should be returned
    assert order_detail["orderId"] == order_id
    assert order_detail["ordererName"] == "Test User"


@pytest.mark.asyncio
async def test_transform_order(manager: CoupangOrderManager):
    # Given: Raw order data from Coupang API
    raw_order = {
        "orderId": 12345,
        "orderedAt": "2023-01-15T10:30:00Z",
        "ordererName": "김쿠팡",
        "ordererPhoneNumber": "010-1234-5678",
        "receiverName": "박쿠팡",
        "receiverPhoneNumber1": "010-9876-5432",
        "receiverPostCode": "01234",
        "receiverAddr1": "서울시 강남구",
        "receiverAddr2": "테헤란로 123",
        "totalPaidAmount": 25000,
        "orderItems": [
            {
                "sellerProductId": "P100",
                "productId": 200,
                "vendorItemId": "V100",
                "sellerProductName": "테스트 상품",
                "vendorItemName": "테스트 상품 - 색상: 레드, 사이즈: M",
                "shippingCount": 1,
                "orderPrice": 22500,
                "discountPrice": 2500,
                "status": "ACCEPT",
            }
        ],
    }

    # When: Transforming the raw order
    order = await manager.transform_order(raw_order)

    # Then: The order model should be correctly populated
    assert order.id == "CP12345"
    assert order.marketplace_order_id == "12345"
    assert order.status == OrderStatus.CONFIRMED
    assert len(order.items) == 1
    assert order.items[0].product_name == "테스트 상품"
    assert order.items[0].options == {"색상": "레드", "사이즈": "M"}
    assert order.items[0].unit_price == Decimal("22500")
    assert order.customer.name == "김쿠팡"
    assert order.customer.recipient_name == "박쿠팡"
    assert order.payment.total_amount == Decimal("25000")


@pytest.mark.asyncio
@respx.mock
async def test_update_tracking_info_success(manager: CoupangOrderManager):
    # Given: Mock a successful shipment update response
    order_id = "54321"
    base_url = manager.base_url
    path = (
        f"/v2/providers/openapi/apis/api/v4/vendors/{manager.vendor_id}/orders/{order_id}/shipment"
    )
    respx.post(f"{base_url}{path}").mock(return_value=Response(200, json={"code": "SUCCESS"}))

    # When: Updating tracking info
    success = await manager.update_tracking_info(order_id, "CJ대한통운", "1234567890")

    # Then: The operation should be successful
    assert success is True


@pytest.mark.asyncio
@respx.mock
async def test_confirm_order_success(manager: CoupangOrderManager):
    # Given: Mock a successful order confirmation response
    order_id = "67890"
    base_url = manager.base_url
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{manager.vendor_id}/orders/{order_id}/acknowledgement"
    respx.put(f"{base_url}{path}").mock(return_value=Response(200, json={"code": "SUCCESS"}))

    # When: Confirming the order
    success = await manager._confirm_order(order_id)

    # Then: The operation should be successful
    assert success is True


def test_create_auth_headers(manager: CoupangOrderManager):
    # Given: A request's components
    method = "GET"
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{manager.vendor_id}/ordersheets"
    params = {"vendorId": manager.vendor_id, "status": "ALL"}
    body = ""

    # When: Creating auth headers
    headers = manager._create_auth_headers(method, path, params, body)

    # Then: The Authorization header should be correctly formatted
    assert "Authorization" in headers
    auth_header = headers["Authorization"]
    assert auth_header.startswith("CEA algorithm=HmacSHA256")
    assert f"access-key={manager.api_key}" in auth_header
    assert "signed-date=" in auth_header
    assert "signature=" in auth_header
