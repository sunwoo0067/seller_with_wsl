"""
BaseUploader 테스트
"""

import asyncio
from unittest.mock import Mock

import pytest

from dropshipping.models.product import ProductImage, StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import BaseUploader, MarketplaceType, UploadStatus


class TestBaseUploader:
    """BaseUploader 테스트"""

    class MockUploader(BaseUploader):
        """테스트용 Mock 업로더"""

        async def validate_product(self, product):
            if not product.name:
                return False, "상품명 누락"
            return True, None

        async def transform_product(self, product):
            return {"name": product.name, "price": int(product.price)}

        async def upload_single(self, product_data):
            return {"success": True, "product_id": "MP001"}

        async def update_single(self, marketplace_product_id, product_data):
            return {"success": True, "product_id": marketplace_product_id}

        async def check_product_status(self, marketplace_product_id):
            return {"success": True, "status": "SALE"}

    @pytest.fixture
    def mock_storage(self):
        """Mock 저장소"""
        return Mock(spec=BaseStorage)

    @pytest.fixture
    def uploader(self, mock_storage):
        """테스트용 업로더"""
        config = {"api_key": "test_key", "api_secret": "test_secret", "batch_size": 5}
        return self.MockUploader(
            marketplace=MarketplaceType.COUPANG, storage=mock_storage, config=config
        )

    @pytest.fixture
    def sample_product(self):
        """테스트용 상품"""
        return StandardProduct(
            id="test-001",
            supplier_id="domeme",
            supplier_product_id="DM001",
            name="테스트 상품",
            price=10000,
            cost=5000,
            category_name="전자기기",
            stock=100,
            images=[ProductImage(url="https://example.com/image1.jpg", is_main=True)],
        )

    def test_init(self, uploader):
        """초기화 테스트"""
        assert uploader.marketplace == MarketplaceType.COUPANG
        assert uploader.api_key == "test_key"
        assert uploader.api_secret == "test_secret"
        assert uploader.batch_size == 5
        assert uploader.stats["uploaded"] == 0

    def test_upload_product_success(self, uploader, sample_product):
        """상품 업로드 성공 테스트"""
        result = asyncio.run(uploader.upload_product(sample_product))

        assert result["product_id"] == "test-001"
        assert result["status"] == UploadStatus.SUCCESS
        assert result["marketplace"] == "coupang"
        assert result["marketplace_product_id"] == "MP001"
        assert result["errors"] == []
        assert result["uploaded_at"] is not None
        assert uploader.stats["uploaded"] == 1

    def test_upload_product_validation_fail(self, uploader):
        """상품 검증 실패 테스트"""
        invalid_product = StandardProduct(
            id="test-002",
            supplier_id="domeme",
            supplier_product_id="DM002",
            name="",  # 빈 상품명
            price=10000,
            cost=5000,
            category_name="전자기기",
            stock=100,
        )

        result = asyncio.run(uploader.upload_product(invalid_product))

        assert result["status"] == UploadStatus.FAILED
        assert "상품명 누락" in result["errors"][0]
        assert uploader.stats["failed"] == 1

    def test_upload_batch(self, uploader, sample_product):
        """배치 업로드 테스트"""
        products = [
            sample_product,
            StandardProduct(
                id="test-003",
                supplier_id="domeme",
                supplier_product_id="DM003",
                name="테스트 상히 2",
                price=20000,
                cost=10000,
                category_name="전자기기",
                stock=50,
            ),
        ]

        results = asyncio.run(uploader.upload_batch(products, max_concurrent=2))

        assert len(results) == 2
        assert all(r["status"] == UploadStatus.SUCCESS for r in results)
        assert uploader.stats["uploaded"] == 2

    def test_upload_batch_with_errors(self, uploader, sample_product):
        """오류가 있는 배치 업로드 테스트"""

        # upload_product 메서드를 Mock하여 예외 발생
        async def mock_upload_with_error(product, update_existing=True):
            if product.id == "test-001":
                return {
                    "product_id": product.id,
                    "status": UploadStatus.SUCCESS,
                    "marketplace": "coupang",
                    "marketplace_product_id": "MP001",
                    "errors": [],
                }
            else:
                raise Exception("업로드 오류")

        uploader.upload_product = mock_upload_with_error

        products = [
            sample_product,
            StandardProduct(
                id="error-001",
                supplier_id="domeme",
                supplier_product_id="DM999",
                name="오류 상품",
                price=20000,
                cost=10000,
                category_name="전자기기",
                stock=50,
            ),
        ]

        results = asyncio.run(uploader.upload_batch(products))

        assert len(results) == 2
        assert results[0]["status"] == UploadStatus.SUCCESS
        assert results[1]["status"] == UploadStatus.FAILED
        assert "업로드 오류" in results[1]["errors"][0]

    def test_validate_api_credentials(self, uploader):
        """API 자격증명 검증 테스트"""
        assert uploader.validate_api_credentials() is True

        # API 키가 없는 경우
        uploader.api_key = None
        assert uploader.validate_api_credentials() is False

    def test_get_stats(self, uploader):
        """통계 조회 테스트"""
        uploader.stats["uploaded"] = 8
        uploader.stats["failed"] = 2

        stats = uploader.get_stats()

        assert stats["uploaded"] == 8
        assert stats["failed"] == 2
        assert stats["total"] == 10
        assert stats["success_rate"] == 0.8
        assert stats["marketplace"] == "coupang"

    def test_reset_stats(self, uploader):
        """통계 초기화 테스트"""
        uploader.stats["uploaded"] = 10
        uploader.stats["failed"] = 5

        uploader.reset_stats()

        assert uploader.stats["uploaded"] == 0
        assert uploader.stats["failed"] == 0
        assert uploader.stats["errors"] == []
