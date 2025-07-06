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


@pytest.mark.asyncio
@respx.mock
async def test_fetch_order_detail_success(manager: ElevenstOrderManager, respx_mock):
    """주문 상세 조회 성공 테스트"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = f"""
    <orders>
        <order>
            <ordNo>{marketplace_order_id}</ordNo>
            <ordPrdNo>1234567890</ordPrdNo>
            <prdNm>테스트 상품</prdNm>
            <ordStlEndDt>2023-11-11 10:00:00</ordStlEndDt>
        </order>
    </orders>
    """
    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}"
    respx_mock.get(url).mock(
        return_value=Response(200, text=mock_xml_response)
    )

    order_detail = await manager.fetch_order_detail(marketplace_order_id)

    assert order_detail["ordNo"] == marketplace_order_id
    assert order_detail["prdNm"] == "테스트 상품"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_order_detail_api_error(manager: ElevenstOrderManager, respx_mock):
    """주문 상세 조회 API 에러 테스트"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = """
    <ErrorMessage>
        <httpStatus>400</httpStatus>
        <message>잘못된 요청입니다.</message>
    </ErrorMessage>
    """
    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}"
    respx_mock.get(url).mock(
        return_value=Response(200, text=mock_xml_response)
    )

    with pytest.raises(Exception, match="11st API Error: 잘못된 요청입니다."):
        await manager.fetch_order_detail(marketplace_order_id)


@pytest.mark.asyncio
@respx.mock
async def test_update_tracking_info_success(manager: ElevenstOrderManager, respx_mock):
    """송장 정보 업데이트 성공 테스트"""
    marketplace_order_id = "2023111112345"
    carrier = "CJ대한통운"
    tracking_number = "123456789012"
    carrier_code = "00034"

    mock_xml_request = f'<?xml version="1.0" encoding="UTF-8"?><deliveryInfo><dlvEtprsCd>{carrier_code}</dlvEtprsCd><invcNo>{tracking_number}</invcNo></deliveryInfo>'
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>0</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/delivery"
    respx_mock.put(url, content=mock_xml_request).mock(
        return_value=Response(200, text=mock_xml_response)
    )

    result = await manager.update_tracking_info(marketplace_order_id, carrier, tracking_number)
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_update_tracking_info_failure(manager: ElevenstOrderManager, respx_mock):
    """송장 정보 업데이트 실패 테스트 (API가 실패 코드 반환)"""
    marketplace_order_id = "2023111112345"
    carrier = "CJ대한통운"
    tracking_number = "123456789012"
    carrier_code = "00034"

    mock_xml_request = f'<?xml version="1.0" encoding="UTF-8"?><deliveryInfo><dlvEtprsCd>{carrier_code}</dlvEtprsCd><invcNo>{tracking_number}</invcNo></deliveryInfo>'
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>Fail</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/delivery"
    respx_mock.put(url, content=mock_xml_request).mock(
        return_value=Response(200, text=mock_xml_response)
    )

    result = await manager.update_tracking_info(marketplace_order_id, carrier, tracking_number)
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_update_tracking_info_http_error(manager: ElevenstOrderManager, respx_mock):
    """송장 정보 업데이트 실패 테스트 (HTTP 에러)"""
    marketplace_order_id = "2023111112345"
    carrier = "CJ대한통운"
    tracking_number = "123456789012"

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/delivery"
    respx_mock.put(url).mock(return_value=Response(500))

    result = await manager.update_tracking_info(marketplace_order_id, carrier, tracking_number)
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_cancel_order_success(manager: ElevenstOrderManager, respx_mock):
    """주문 취소 성공 테스트"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>0</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/cancel"
    respx_mock.post(url).mock(return_value=Response(200, text=mock_xml_response))

    result = await manager._cancel_order(marketplace_order_id)
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_cancel_order_failure(manager: ElevenstOrderManager, respx_mock):
    """주문 취소 실패 테스트 (API 실패)"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>Fail</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/cancel"
    respx_mock.post(url).mock(return_value=Response(200, text=mock_xml_response))

    result = await manager._cancel_order(marketplace_order_id)
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_cancel_order_http_error(manager: ElevenstOrderManager, respx_mock):
    """주문 취소 실패 테스트 (HTTP 에러)"""
    marketplace_order_id = "2023111112345"

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/cancel"
    respx_mock.post(url).mock(return_value=Response(500))

    result = await manager._cancel_order(marketplace_order_id)
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_return_order_success(manager: ElevenstOrderManager, respx_mock):
    """주문 반품 성공 테스트"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>0</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/return"
    respx_mock.post(url).mock(return_value=Response(200, text=mock_xml_response))

    result = await manager._return_order(marketplace_order_id)
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_return_order_failure(manager: ElevenstOrderManager, respx_mock):
    """주문 반품 실패 테스트 (API 실패)"""
    marketplace_order_id = "2023111112345"
    mock_xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ClientMessage>
        <resultCode>Fail</resultCode>
    </ClientMessage>"""

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/return"
    respx_mock.post(url).mock(return_value=Response(200, text=mock_xml_response))

    result = await manager._return_order(marketplace_order_id)
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_return_order_http_error(manager: ElevenstOrderManager, respx_mock):
    """주문 반품 실패 테스트 (HTTP 에러)"""
    marketplace_order_id = "2023111112345"

    url = f"{manager.base_url}/openapi/v1/orders/{marketplace_order_id}/return"
    respx_mock.post(url).mock(return_value=Response(500))

    result = await manager._return_order(marketplace_order_id)
    assert result is False


