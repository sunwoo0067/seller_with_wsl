import pytest
import respx
from httpx import Response
from datetime import datetime, timedelta

from dropshipping.orders.elevenst.elevenst_order_manager import ElevenstOrderManager
from dropshipping.models.order import OrderStatus


@pytest.fixture
def manager(mocker):
    mock_storage = mocker.Mock()
    return ElevenstOrderManager(
        storage=mock_storage,
        config={"api_key": "test_api_key"}
    )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orders_success(manager: ElevenstOrderManager):
    """fetch_orders 성공 케이스 테스트"""
    start_date = datetime.now() - timedelta(days=1)
    end_date = datetime.now()

    mock_xml_response = f"""<?xml version='1.0' encoding='UTF-8'?>
    <orders>
        <order>
            <ordNo>12345</ordNo>
            <ordPrdNo>67890</ordPrdNo>
            <prdNm>Test Product</prdNm>
            <ordDtm>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</ordDtm>
            <ordStlEndDtm>{(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')}</ordStlEndDtm>
            <ordStatus>202</ordStatus> 
        </order>
    </orders>"""

    url = f"{manager.base_url}/openapi/v1/orders"
    respx.get(url).mock(return_value=Response(200, text=mock_xml_response))

    orders = await manager.fetch_orders(start_date, end_date, status=OrderStatus.PENDING)

    assert len(orders) == 1
    assert orders[0]["ordNo"] == "12345"
    assert orders[0]["prdNm"] == "Test Product"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_orders_api_error(manager: ElevenstOrderManager):
    """fetch_orders API 에러 케이스 테스트"""
    start_date = datetime.now() - timedelta(days=1)
    end_date = datetime.now()

    mock_xml_error = """<?xml version='1.0' encoding='UTF-8'?>
    <ErrorMessage>
        <httpStatus>401</httpStatus>
        <errorCode>E001</errorCode>
        <message>인증키가 유효하지 않습니다.</message>
    </ErrorMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders"
    respx.get(url).mock(return_value=Response(200, text=mock_xml_error))

    with pytest.raises(Exception, match="11st API Error: 인증키가 유효하지 않습니다."):
        await manager.fetch_orders(start_date, end_date)
