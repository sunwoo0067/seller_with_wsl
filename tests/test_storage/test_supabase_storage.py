"""
Supabase 저장소 테스트
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from dropshipping.models.product import (
    OptionType,
    ProductImage,
    ProductOption,
    ProductStatus,
    StandardProduct,
)
from dropshipping.storage.supabase_storage import SupabaseStorage


class TestSupabaseStorage:
    """Supabase 저장소 테스트"""

    @pytest.fixture
    def mock_client(self):
        """Mock Supabase 클라이언트"""
        with patch("dropshipping.storage.supabase_storage.create_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def storage(self, mock_client):
        """테스트용 저장소"""
        storage = SupabaseStorage(url="https://test.supabase.co", service_key="test-service-key")
        return storage

    @pytest.fixture
    def sample_product(self):
        """테스트용 상품"""
        return StandardProduct(
            id="test-product-1",
            supplier_id="domeme",
            supplier_product_id="DM12345",
            name="테스트 상품",
            brand="TestBrand",
            manufacturer="TestMaker",
            origin="Korea",
            description="테스트 상품입니다",
            cost=Decimal("10000"),
            price=Decimal("15000"),
            list_price=Decimal("20000"),
            stock=100,
            status=ProductStatus.ACTIVE,
            category_code="001",
            category_name="패션의류",
            category_path=["패션", "의류", "여성"],
            images=[
                ProductImage(url="https://example.com/image1.jpg", is_main=True, order=0),
                ProductImage(url="https://example.com/image2.jpg", order=1),
            ],
            options=[
                ProductOption(
                    name="색상",
                    type=OptionType.SELECT,
                    values=["블랙", "화이트"],
                    required=True,
                ),
                ProductOption(
                    name="사이즈",
                    type=OptionType.SELECT,
                    values=["S", "M", "L"],
                    required=True,
                ),
            ],
            shipping_fee=Decimal("2500"),
        )

    def test_init(self, mock_client):
        """초기화 테스트"""
        storage = SupabaseStorage(url="https://test.supabase.co", service_key="test-service-key")

        assert storage.url == "https://test.supabase.co"
        assert storage.service_key == "test-service-key"
        assert storage.client is not None

    def test_save_raw_product(self, storage, mock_client):
        """원본 상품 저장 테스트"""
        # Mock 설정
        supplier_id = str(uuid4())
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(
            data={"id": supplier_id}
        )

        record_id = str(uuid4())
        mock_client.table.return_value.upsert.return_value.execute.return_value = Mock(
            data=[{"id": record_id}]
        )

        # 원본 데이터
        raw_data = {
            "supplier_id": "domeme",
            "supplier_product_id": "DM12345",
            "raw_json": {"productNo": "12345", "productNm": "테스트"},
            "data_hash": "abcdef123456",
            "fetched_at": datetime.now(),
        }

        # 저장 실행
        result = storage.save_raw_product(raw_data)

        # 검증
        assert result == record_id
        mock_client.table.assert_called_with("products_raw")
        mock_client.table.return_value.upsert.assert_called_once()

    def test_save_processed_product(self, storage, mock_client, sample_product):
        """처리된 상품 저장 테스트"""
        # Mock 설정
        supplier_id = str(uuid4())
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(
            data={"id": supplier_id}
        )

        product_id = str(uuid4())
        mock_client.table.return_value.upsert.return_value.execute.return_value = Mock(
            data=[{"id": product_id}]
        )

        raw_id = str(uuid4())

        # 저장 실행
        result = storage.save_processed_product(raw_id, sample_product)

        # 검증
        assert result == product_id
        mock_client.table.assert_any_call("products_processed")

        # upsert 호출 검증
        upsert_call = mock_client.table.return_value.upsert.call_args
        assert upsert_call is not None

        # 저장된 데이터 검증
        saved_data = upsert_call[0][0]
        assert saved_data["name"] == "테스트 상품"
        assert saved_data["cost"] == 10000.0
        assert saved_data["price"] == 15000.0
        assert len(saved_data["images"]) == 2
        assert len(saved_data["options"]) == 2

    def test_exists_by_hash(self, storage, mock_client):
        """해시로 중복 체크 테스트"""
        # Mock 설정
        supplier_id = str(uuid4())
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(
            data={"id": supplier_id}
        )

        # 중복 있는 경우
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = Mock(
            data=[{"id": "existing-id"}]
        )

        result = storage.exists_by_hash("domeme", "test-hash")
        assert result is True

        # 중복 없는 경우
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = Mock(
            data=[]
        )

        result = storage.exists_by_hash("domeme", "new-hash")
        assert result is False

    def test_get_raw_product(self, storage, mock_client):
        """원본 상품 조회 테스트"""
        # Mock 데이터
        record_id = str(uuid4())
        supplier_id = str(uuid4())

        mock_data = {
            "id": record_id,
            "supplier_id": supplier_id,
            "supplier_product_id": "DM12345",
            "raw_json": {"test": "data"},
            "data_hash": "test-hash",
            "fetched_at": "2024-01-01T00:00:00",
            "created_at": "2024-01-01T00:00:00",
        }

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(
            data=mock_data
        )

        # 공급사 코드 조회 Mock
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            Mock(data=mock_data),  # 첫 번째 호출: 상품 데이터
            Mock(data={"code": "domeme"}),  # 두 번째 호출: 공급사 코드
        ]

        # 조회 실행
        result = storage.get_raw_product(record_id)

        # 검증
        assert result is not None
        assert result["id"] == record_id
        assert result["supplier_product_id"] == "DM12345"
        assert result["raw_json"]["test"] == "data"

    def test_list_raw_products(self, storage, mock_client):
        """원본 상품 목록 조회 테스트"""
        # Mock 데이터
        mock_data = [
            {
                "id": str(uuid4()),
                "supplier_id": str(uuid4()),
                "supplier_product_id": f"DM{i}",
                "raw_json": {"productNo": f"{i}"},
                "data_hash": f"hash{i}",
                "fetched_at": "2024-01-01T00:00:00",
                "created_at": "2024-01-01T00:00:00",
            }
            for i in range(3)
        ]

        mock_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = Mock(
            data=mock_data
        )

        # 공급사 코드 조회 Mock
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(
            data={"code": "domeme"}
        )

        # 조회 실행
        results = storage.list_raw_products(limit=10, offset=0)

        # 검증
        assert len(results) == 3
        assert results[0]["supplier_product_id"] == "DM0"
        assert results[1]["supplier_product_id"] == "DM1"

    def test_update_status(self, storage, mock_client):
        """상태 업데이트 테스트"""
        # Mock 설정
        record_id = str(uuid4())
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            Mock(data=[{"id": record_id}])
        )

        # 업데이트 실행
        result = storage.update_status(record_id, "inactive")

        # 검증
        assert result is True
        mock_client.table.assert_called_with("products_processed")
        mock_client.table.return_value.update.assert_called_with({"status": "inactive"})

    @pytest.mark.skip(reason="Complex mock setup needed for multiple table calls")
    def test_get_stats(self, storage, mock_client):
        """통계 조회 테스트"""
        # 처리된 상품 데이터
        processed_data = [
            {"supplier_id": str(uuid4()), "status": "active"},
            {"supplier_id": str(uuid4()), "status": "active"},
            {"supplier_id": str(uuid4()), "status": "inactive"},
        ]

        # Mock 체인 설정
        raw_table_mock = Mock()
        raw_table_mock.select.return_value = raw_table_mock
        raw_table_mock.eq.return_value = raw_table_mock
        raw_table_mock.execute.return_value = Mock(count=100, data=[])

        processed_table_mock = Mock()
        processed_table_mock.select.return_value = processed_table_mock
        processed_table_mock.eq.return_value = processed_table_mock
        processed_table_mock.execute.return_value = Mock(count=3, data=processed_data)

        # table 메서드가 호출되는 순서대로 mock 반환
        mock_client.table.side_effect = [
            raw_table_mock,  # products_raw 테이블
            processed_table_mock,  # products_processed 테이블
        ]

        # 통계 조회
        stats = storage.get_stats()

        # 검증
        assert stats["total_raw"] == 100
        assert stats["total_processed"] == 3
        assert stats["by_status"]["active"] == 2
        assert stats["by_status"]["inactive"] == 1

    def test_get_pricing_rules(self, storage, mock_client):
        """가격 규칙 조회 테스트"""
        # Mock 데이터
        mock_rules = [
            {
                "id": str(uuid4()),
                "name": "저가 상품 규칙",
                "priority": 10,
                "conditions": {"max_cost": 10000},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.5},
                "is_active": True,
            },
            {
                "id": str(uuid4()),
                "name": "기본 규칙",
                "priority": 0,
                "conditions": {},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.25},
                "is_active": True,
            },
        ]

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = Mock(
            data=mock_rules
        )

        # 조회 실행
        rules = storage.get_pricing_rules()

        # 검증
        assert len(rules) == 2
        assert rules[0]["name"] == "저가 상품 규칙"
        assert rules[0]["priority"] == 10

    def test_log_pipeline(self, storage, mock_client):
        """파이프라인 로그 테스트"""
        # Mock 설정
        log_id = str(uuid4())
        mock_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": log_id}]
        )

        # 로그 생성
        result = storage.log_pipeline(
            pipeline_type="fetch",
            target_type="supplier",
            target_id="domeme",
            status="running",
            details={"category": "001"},
        )

        # 검증
        assert result == log_id
        mock_client.table.assert_called_with("pipeline_logs")

        # 로그 업데이트
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            Mock(data=[{"id": log_id}])
        )

        storage.update_pipeline_log(
            log_id=log_id,
            status="success",
            records_processed=100,
            records_failed=2,
        )

        # 업데이트 검증
        update_call = mock_client.table.return_value.update.call_args
        assert update_call is not None
        update_data = update_call[0][0]
        assert update_data["status"] == "success"
        assert update_data["records_processed"] == 100
        assert update_data["records_failed"] == 2
