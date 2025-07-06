import pytest
from unittest.mock import Mock

from dropshipping.transformers.category_mapper import CategoryMapper
from dropshipping.storage.supabase_storage import SupabaseStorage


@pytest.fixture
def mock_supabase_storage():
    """SupabaseStorage를 Mocking하는 픽스처"""
    mock_storage = Mock(spec=SupabaseStorage)
    mock_storage.get_all_category_mappings.return_value = [
        {
            "supplier_id": "domeme",
            "marketplace_id": "coupang",
            "supplier_category_code": "D100",
            "marketplace_category_code": "C100",
        },
        {
            "supplier_id": "domeme",
            "marketplace_id": "coupang",
            "supplier_category_code": "D200",
            "marketplace_category_code": "C200",
        },
        {
            "supplier_id": "ownerclan",
            "marketplace_id": "coupang",
            "supplier_category_code": "O300",
            "marketplace_category_code": "C300",
        },
    ]
    return mock_storage


@pytest.fixture
def category_mapper(mock_supabase_storage):
    """CategoryMapper 인스턴스 픽스처"""
    return CategoryMapper(mock_supabase_storage)


def test_get_market_code_existing_mapping(category_mapper):
    """기존 매핑이 있는 경우 올바른 마켓 코드 반환 테스트"""
    result = category_mapper.get_market_code("domeme", "coupang", "D100")
    assert result == "C100"


def test_get_market_code_no_mapping(category_mapper):
    """매핑이 없는 경우 None 반환 테스트"""
    result = category_mapper.get_market_code("domeme", "coupang", "D999")
    assert result is None


def test_get_market_code_different_supplier(category_mapper):
    """다른 공급사 매핑 테스트"""
    result = category_mapper.get_market_code("ownerclan", "coupang", "O300")
    assert result == "C300"


def test_get_market_code_different_marketplace(category_mapper):
    """다른 마켓플레이스 매핑 테스트 (현재 데이터에 없음)"""
    result = category_mapper.get_market_code("domeme", "elevenst", "D100")
    assert result is None


def test_reload_mappings(category_mapper, mock_supabase_storage):
    """매핑 재로드 테스트"""
    # 초기 로드 확인
    assert category_mapper.get_market_code("domeme", "coupang", "D100") == "C100"

    # Mock 데이터 변경
    mock_supabase_storage.get_all_category_mappings.return_value = [
        {
            "supplier_id": "domeme",
            "marketplace_id": "coupang",
            "supplier_category_code": "D100",
            "marketplace_category_code": "NEW_C100",
        },
    ]

    # 매핑 재로드
    category_mapper.reload_mappings()

    # 변경된 매핑 확인
    assert category_mapper.get_market_code("domeme", "coupang", "D100") == "NEW_C100"
    assert category_mapper.get_market_code("domeme", "coupang", "D200") is None
