import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import requests

from dropshipping.suppliers.domeme.fetcher import DomemeFetcher
from dropshipping.storage.supabase_storage import SupabaseStorage
from dropshipping.config import settings

@pytest.fixture
def mock_domeme_settings():
    """도매매 API 키 설정을 Mock"""
    with patch('dropshipping.config.DomemeConfig') as MockDomemeConfig:
        mock_domeme_instance = Mock()
        mock_domeme_instance.api_key = "test_domeme_api_key"
        mock_domeme_instance.api_url = "http://test.domeme.com/domeme/api/v1/"
        MockDomemeConfig.return_value = mock_domeme_instance
        yield

@pytest.fixture
def mock_supabase_storage():
    """SupabaseStorage를 Mocking하는 픽스처"""
    mock_storage = Mock(spec=SupabaseStorage)
    mock_storage.save_raw_product.return_value = "mock_id"
    mock_storage.exists_by_hash.return_value = False
    return mock_storage

@pytest.fixture
def domeme_fetcher(mock_supabase_storage, mock_domeme_settings):
    """DomemeFetcher 인스턴스 픽스처"""
    return DomemeFetcher(
        storage=mock_supabase_storage,
        supplier_name="domeme",
        api_key="test-api-key",
        api_url="https://test.api.com"
    )

@pytest.fixture
def mock_requests_get():
    """requests.get을 Mock"""
    with patch('requests.get') as mock_get:
        yield mock_get

def test_fetch_list_success(domeme_fetcher, mock_requests_get):
    """fetch_list 성공 테스트"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product>
                <productNo>P1</productNo>
                <productNm>상품1</productNm>
                <supplyPrice>10000</supplyPrice>
                <regDate>20250701100000</regDate>
            </product>
            <product>
                <productNo>P2</productNo>
                <productNm>상품2</productNm>
                <supplyPrice>20000</supplyPrice>
                <regDate>20250702100000</regDate>
            </product>
        </productList>
    </result>"""
    mock_requests_get.return_value = mock_response

    products = domeme_fetcher.fetch_list(1)

    assert len(products) == 2
    assert products[0]['id'] == 'P1'
    assert products[1]['productNm'] == '상품2'
    mock_requests_get.assert_called_once_with(
        "http://test.domeme.com/domeme/api/v1/searchProductList",
        params={'apiKey': 'test_domeme_api_key', 'ver': '4.1', 'page': 1, 'pageSize': 100, 'market': 'supply'},
        timeout=10
    )

def test_fetch_list_api_failure(domeme_fetcher, mock_requests_get):
    """fetch_list API 호출 실패 테스트"""
    mock_requests_get.side_effect = requests.exceptions.RequestException("API Error")

    products = domeme_fetcher.fetch_list(1)

    assert len(products) == 0

def test_fetch_list_xml_error(domeme_fetcher, mock_requests_get):
    """fetch_list XML 파싱 에러 테스트"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<invalid_xml>"
    mock_requests_get.return_value = mock_response

    products = domeme_fetcher.fetch_list(1)

    assert len(products) == 0

def test_fetch_detail_success(domeme_fetcher, mock_requests_get):
    """fetch_detail 성공 테스트"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <product>
            <productNo>P1</productNo>
            <productNm>상품1 상세</productNm>
            <price>15000</price>
        </product>
    </result>"""
    mock_requests_get.return_value = mock_response

    detail = domeme_fetcher.fetch_detail('P1')

    assert detail['id'] == 'P1'
    assert detail['productNm'] == '상품1 상세'
    mock_requests_get.assert_called_once_with(
        "http://test.domeme.com/domeme/api/v1/searchProductInfo",
        params={'apiKey': 'test_domeme_api_key', 'ver': '4.5', 'productNo': 'P1'},
        timeout=10
    )

def test_fetch_detail_api_failure(domeme_fetcher, mock_requests_get):
    """fetch_detail API 호출 실패 테스트"""
    mock_requests_get.side_effect = requests.exceptions.RequestException("API Error")

    detail = domeme_fetcher.fetch_detail('P1')

    assert detail == {}

def test_run_incremental_new_items(domeme_fetcher, mock_requests_get, mock_supabase_storage):
    """run_incremental 새 상품 수집 테스트"""
    # fetch_list Mock
    list_response_page1 = Mock()
    list_response_page1.status_code = 200
    list_response_page1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product><productNo>NEW1</productNo><regDate>20250705120000</regDate></product>
            <product><productNo>NEW2</productNo><regDate>20250705110000</regDate></product>
        </productList>
    </result>"""

    list_response_page2 = Mock()
    list_response_page2.status_code = 200
    list_response_page2.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product><productNo>OLD1</productNo><regDate>20250704100000</regDate></product>
        </productList>
    </result>"""

    list_response_page3 = Mock()
    list_response_page3.status_code = 200
    list_response_page3.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result><code>00</code><message>성공</message><productList/></result>"""

    # fetch_detail Mock
    detail_response_new1 = Mock()
    detail_response_new1.status_code = 200
    detail_response_new1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result><code>00</code><message>성공</message><product><productNo>NEW1</productNo><name>New Product 1</name></product></result>"""

    detail_response_new2 = Mock()
    detail_response_new2.status_code = 200
    detail_response_new2.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result><code>00</code><message>성공</message><product><productNo>NEW2</productNo><name>New Product 2</name></product></result>"""

    detail_response_old1 = Mock()
    detail_response_old1.status_code = 200
    detail_response_old1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result><code>00</code><message>성공</message><product><productNo>OLD1</productNo><name>Old Product 1</name></product></result>"""

    mock_requests_get.side_effect = [
        list_response_page1, # fetch_list(1)
        detail_response_new1, # fetch_detail(NEW1)
        detail_response_new2, # fetch_detail(NEW2)
        list_response_page2, # fetch_list(2)
        detail_response_old1, # fetch_detail(OLD1)
        list_response_page3, # fetch_list(3) - no more items
    ]

    # since 날짜를 현재 날짜보다 이전으로 설정하여 새 상품만 가져오도록 함
    domeme_fetcher.run_incremental("domeme", since=datetime(2025, 7, 4, 23, 59, 59))

    # NEW1, NEW2만 저장되어야 함
    assert mock_supabase_storage.save_raw_product.call_count == 2
    args, kwargs = mock_supabase_storage.save_raw_product.call_args_list[0]
    assert kwargs['raw_data']['supplier_product_id'] == 'NEW1'
    args, kwargs = mock_supabase_storage.save_raw_product.call_args_list[1]
    assert kwargs['raw_data']['supplier_product_id'] == 'NEW2'

def test_run_incremental_old_items_stop(domeme_fetcher, mock_requests_get, mock_supabase_storage):
    """run_incremental 오래된 상품 발견 시 중단 테스트"""
    # fetch_list Mock
    list_response_page1 = Mock()
    list_response_page1.status_code = 200
    list_response_page1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product><productNo>NEW1</productNo><regDate>20250705120000</regDate></product>
            <product><productNo>OLD1</productNo><regDate>20250704100000</regDate></product>
        </productList>
    </result>"""

    # fetch_detail Mock
    detail_response_new1 = Mock()
    detail_response_new1.status_code = 200
    detail_response_new1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result><code>00</code><message>성공</message><product><productNo>NEW1</productNo><name>New Product 1</name></product></result>"""

    mock_requests_get.side_effect = [
        list_response_page1, # fetch_list(1)
        detail_response_new1, # fetch_detail(NEW1)
    ]

    # since 날짜를 OLD1의 regDate와 동일하게 설정하여 OLD1에서 중단되도록 함
    domeme_fetcher.run_incremental("domeme", since=datetime(2025, 7, 4, 10, 0, 0))

    # NEW1만 저장되어야 함
    assert mock_supabase_storage.save_raw_product.call_count == 1
    args, kwargs = mock_supabase_storage.save_raw_product.call_args_list[0]
    assert kwargs['raw_data']['supplier_product_id'] == 'NEW1'

def test_run_incremental_no_new_items(domeme_fetcher, mock_requests_get, mock_supabase_storage):
    """run_incremental 새 상품이 없을 때 테스트"""
    # fetch_list Mock
    list_response_page1 = Mock()
    list_response_page1.status_code = 200
    list_response_page1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product><productNo>OLD1</productNo><regDate>20250704100000</regDate></product>
        </productList>
    </result>"""

    mock_requests_get.side_effect = [
        list_response_page1, # fetch_list(1)
    ]

    # since 날짜를 현재 날짜보다 이후로 설정하여 아무것도 가져오지 않도록 함
    domeme_fetcher.run_incremental("domeme", since=datetime(2025, 7, 5, 10, 0, 0))

    # 아무것도 저장되지 않아야 함
    mock_supabase_storage.save_raw_product.assert_not_called()

