from unittest.mock import MagicMock, patch

import pytest

from dropshipping.suppliers.domeme.client import DomemeAPIError
from dropshipping.suppliers.domeme.fetcher import DomemeFetcher


# Mock 데이터
@pytest.fixture
def mock_domeme_client():
    """DomemeClient의 Mock 객체"""
    client = MagicMock()

    # fetch_list에 대한 Mock 설정
    def mock_search_products(page=1, **kwargs):
        if page > 1:
            return {"products": [], "has_next": False}
        return {
            "products": [
                {"productNo": "1", "productName": "Test Product 1", "price": 10000},
                {"productNo": "2", "productName": "Test Product 2", "price": 20000},
            ],
            "has_next": True,
        }

    client.search_products.side_effect = mock_search_products

    # fetch_detail에 대한 Mock 설정
    client.get_product_detail.return_value = {
        "productNo": "1",
        "description": "Detailed description",
    }

    return client


@pytest.fixture
def mock_storage():
    """BaseStorage의 Mock 객체"""
    storage = MagicMock()
    storage.exists_by_hash.return_value = False
    storage.save_raw_product.return_value = "mock_record_id"
    return storage


# 테스트 케이스
def test_fetch_list_success(mock_domeme_client, mock_storage):
    """상품 목록 조회 성공 테스트"""
    fetcher = DomemeFetcher(
        storage=mock_storage,
        supplier_name="domeme",
        api_key="test_key",
        api_url="https://test.api.com",
    )
    fetcher.client = mock_domeme_client

    products, has_next = fetcher.fetch_list(page=1)

    assert len(products) == 2
    assert has_next is True
    assert products[0]["productName"] == "Test Product 1"


def test_fetch_list_api_error(mock_domeme_client, mock_storage):
    """상품 목록 조회 API 오류 테스트"""
    mock_domeme_client.search_products.side_effect = DomemeAPIError("API Error")
    fetcher = DomemeFetcher(
        storage=mock_storage,
        supplier_name="domeme",
        api_key="test_key",
        api_url="https://test.api.com",
    )
    fetcher.client = mock_domeme_client

    with pytest.raises(Exception):  # FetchError는 Exception을 상속
        fetcher.fetch_list(page=1)


def test_fetch_detail_success(mock_domeme_client, mock_storage):
    """상품 상세 조회 성공 테스트"""
    fetcher = DomemeFetcher(
        storage=mock_storage,
        supplier_name="domeme",
        api_key="test_key",
        api_url="https://test.api.com",
    )
    fetcher.client = mock_domeme_client

    detail = fetcher.fetch_detail("1")

    assert detail["productNo"] == "1"
    assert "description" in detail


@patch("dropshipping.suppliers.base.base_fetcher.BaseFetcher.is_duplicate")
def test_run_incremental_saves_new_products(mock_is_duplicate, mock_domeme_client, mock_storage):
    """증분 동기화 시 새 상품 저장 테스트"""
    mock_is_duplicate.return_value = False
    fetcher = DomemeFetcher(
        storage=mock_storage,
        supplier_name="domeme",
        api_key="test_key",
        api_url="https://test.api.com",
    )
    fetcher.client = mock_domeme_client

    # 특정 카테고리에 대해서만 실행
    fetcher.run_incremental(max_pages=1, category="001")

    # save_raw가 2번 호출되었는지 확인
    assert mock_storage.save_raw_product.call_count == 2
    assert fetcher.stats["saved"] == 2
    assert fetcher.stats["fetched"] == 2


@patch("dropshipping.suppliers.base.base_fetcher.BaseFetcher.is_duplicate")
def test_run_incremental_skips_duplicates(mock_is_duplicate, mock_domeme_client, mock_storage):
    """증분 동기화 시 중복 상품 스킵 테스트"""
    mock_is_duplicate.return_value = True
    fetcher = DomemeFetcher(
        storage=mock_storage,
        supplier_name="domeme",
        api_key="test_key",
        api_url="https://test.api.com",
    )
    fetcher.client = mock_domeme_client

    # 특정 카테고리에 대해서만 실행
    fetcher.run_incremental(max_pages=1, category="001")

    # save_raw가 호출되지 않았는지 확인
    mock_storage.save_raw_product.assert_not_called()
    assert fetcher.stats["duplicates"] == 2
    assert fetcher.stats["fetched"] == 2
