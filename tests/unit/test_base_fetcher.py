import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from dropshipping.suppliers.base.base_fetcher import BaseFetcher
from dropshipping.storage.supabase_storage import SupabaseStorage

class ConcreteFetcher(BaseFetcher):
    """BaseFetcher를 테스트하기 위한 구체적인 구현체"""
    def __init__(self, storage: SupabaseStorage):
        super().__init__(storage)
        self._list_data = []
        self._detail_data = {}

    def set_list_data(self, data: list):
        self._list_data = data

    def set_detail_data(self, data: dict):
        self._detail_data = data

    def fetch_list(self, page: int) -> list:
        # 페이지네이션을 간단히 시뮬레이션
        items_per_page = 2
        start_index = (page - 1) * items_per_page
        end_index = start_index + items_per_page
        return self._list_data[start_index:end_index]

    def fetch_detail(self, item_id: str) -> dict:
        return self._detail_data.get(item_id, {})

@pytest.fixture
def mock_supabase_storage():
    """SupabaseStorage를 Mocking하는 픽스처"""
    mock_storage = Mock(spec=SupabaseStorage)
    mock_storage.save_raw_product.return_value = "mock_id"
    
    mock_storage.exists_by_hash.return_value = False
    return mock_storage

@pytest.fixture
def concrete_fetcher(mock_supabase_storage):
    """ConcreteFetcher 인스턴스 픽스처"""
    return ConcreteFetcher(mock_supabase_storage)

def test_base_fetcher_abstract_methods():
    """추상 메서드가 구현되지 않으면 TypeError 발생 확인"""
    with pytest.raises(TypeError):
        BaseFetcher(Mock())

def test_calculate_hash(concrete_fetcher):
    """데이터 해시 계산 테스트"""
    data1 = {"key1": "value1", "key2": 123}
    data2 = {"key2": 123, "key1": "value1"} # 키 순서만 다름
    data3 = {"key1": "value1", "key2": 456}

    hash1 = concrete_fetcher._calculate_hash(data1)
    hash2 = concrete_fetcher._calculate_hash(data2)
    hash3 = concrete_fetcher._calculate_hash(data3)

    assert hash1 == hash2
    assert hash1 != hash3

def test_save_raw_success(concrete_fetcher, mock_supabase_storage):
    """_save_raw 메서드 성공 테스트"""
    supplier_id = "test_supplier"
    supplier_product_id = "prod123"
    raw_json = {"data": "test"}

    result = concrete_fetcher._save_raw(supplier_id, supplier_product_id, raw_json)

    mock_supabase_storage.save_raw_product.assert_called_once()
    assert result is True

def test_save_raw_duplicate(concrete_fetcher, mock_supabase_storage):
    """_save_raw 메서드 중복 데이터 테스트"""
    supplier_id = "test_supplier"
    supplier_product_id = "prod123"
    raw_json = {"data": "test"}

    mock_supabase_storage.save_raw_product.side_effect = Exception("duplicate key value violates unique constraint")

    result = concrete_fetcher._save_raw(supplier_id, supplier_product_id, raw_json)

    assert result is False

def test_run_incremental_basic(concrete_fetcher, mock_supabase_storage):
    """run_incremental 기본 동작 테스트"""
    supplier_id = "test_supplier_id"
    
    # Mock 데이터 설정
    concrete_fetcher.set_list_data([
        {"id": "item1"},
        {"id": "item2"},
        {"id": "item3"},
        {"id": "item4"},
    ])
    concrete_fetcher.set_detail_data({
        "item1": {"id": "item1", "name": "Product 1"},
        "item2": {"id": "item2", "name": "Product 2"},
        "item3": {"id": "item3", "name": "Product 3"},
        "item4": {"id": "item4", "name": "Product 4"},
    })

    concrete_fetcher.run_incremental(supplier_id)

    # save_raw_product가 각 아이템에 대해 호출되었는지 확인
    assert mock_supabase_storage.save_raw_product.call_count == 4

def test_run_incremental_no_items(concrete_fetcher, mock_supabase_storage):
    """run_incremental에 아이템이 없을 때 테스트"""
    supplier_id = "test_supplier_id"
    concrete_fetcher.set_list_data([])

    concrete_fetcher.run_incremental(supplier_id)

    mock_supabase_storage.save_raw_product.assert_not_called()

def test_run_incremental_detail_fetch_failure(concrete_fetcher, mock_supabase_storage):
    """run_incremental에서 상세 정보 가져오기 실패 시 테스트"""
    supplier_id = "test_supplier_id"
    concrete_fetcher.set_list_data([
        {"id": "item1"},
        {"id": "item2"},
    ])
    concrete_fetcher.set_detail_data({
        "item1": {"id": "item1", "name": "Product 1"}, # item2는 상세 데이터 없음
    })

    concrete_fetcher.run_incremental(supplier_id)

    # item1만 저장되고 item2는 저장되지 않음
    mock_supabase_storage.save_raw_product.assert_called_once()
    args, kwargs = mock_supabase_storage.save_raw_product.call_args
    assert kwargs['raw_data']['supplier_product_id'] == "item1"

def test_run_incremental_with_since_parameter(concrete_fetcher, mock_supabase_storage):
    """run_incremental의 since 파라미터 동작 테스트 (현재는 TODO)"""
    supplier_id = "test_supplier_id"
    since_date = datetime(2024, 1, 1)

    concrete_fetcher.set_list_data([
        {"id": "item1"},
        {"id": "item2"},
    ])
    concrete_fetcher.set_detail_data({
        "item1": {"id": "item1", "name": "Product 1"},
        "item2": {"id": "item2", "name": "Product 2"},
    })

    concrete_fetcher.run_incremental(supplier_id, since=since_date)

    # 현재 BaseFetcher의 run_incremental은 since 파라미터를 직접 사용하지 않으므로
    # save_raw_product는 여전히 모든 아이템에 대해 호출될 것임
    assert mock_supabase_storage.save_raw_product.call_count == 2

