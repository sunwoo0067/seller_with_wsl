
import pytest
from unittest.mock import MagicMock, patch
import asyncio

from dropshipping.uploader.coupang_api.uploader import CoupangUploader
from dropshipping.uploader.base import UploadStatus, MarketplaceType
from dropshipping.models.product import StandardProduct, ProductImage
from dropshipping.storage.base import BaseStorage

@pytest.fixture
def mock_storage():
    """BaseStorage의 Mock 객체"""
    storage = MagicMock(spec=BaseStorage)
    storage.get_marketplace_upload.return_value = None # 기본적으로 기존 업로드 없음
    storage.save_marketplace_upload.return_value = None
    return storage

@pytest.fixture
def coupang_uploader(mock_storage):
    """테스트용 CoupangUploader 인스턴스"""
    config = {
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
        "vendor_id": "test_vendor_id",
    }
    return CoupangUploader(storage=mock_storage, config=config)

@pytest.fixture
def sample_product():
    """샘플 StandardProduct 객체"""
    return StandardProduct(
        id="prod123",
        supplier_id="domeme",
        supplier_product_id="DM456",
        name="테스트 상품",
        description="테스트 상품 설명",
        cost=Decimal("10000"),
        price=Decimal("15000"),
        stock=10,
        images=[
            ProductImage(url="http://example.com/img1.jpg", is_main=True),
            ProductImage(url="http://example.com/img2.jpg"),
        ],
    )

class TestCoupangUploader:

    @pytest.mark.asyncio
    async def test_validate_product_success(self, coupang_uploader, sample_product):
        """상품 검증 성공 테스트"""
        is_valid, error_msg = await coupang_uploader.validate_product(sample_product)
        assert is_valid is True
        assert error_msg is None

    @pytest.mark.asyncio
    async def test_validate_product_failure(self, coupang_uploader, sample_product):
        """상품 검증 실패 테스트 (상품명 없음)"""
        sample_product.name = ""
        is_valid, error_msg = await coupang_uploader.validate_product(sample_product)
        assert is_valid is False
        assert "상품명이 없습니다." in error_msg

    @pytest.mark.asyncio
    async def test_transform_product(self, coupang_uploader, sample_product):
        """상품 변환 테스트"""
        transformed_data = await coupang_uploader.transform_product(sample_product)
        assert "vendorId" in transformed_data
        assert transformed_data["sellerProductName"] == "테스트 상품"
        assert len(transformed_data["images"]) == 2
        assert len(transformed_data["items"]) == 1 # 옵션 없는 경우

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_single_success(self, mock_api_request, coupang_uploader, sample_product):
        """단일 상품 업로드 성공 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS", "data": {"productId": "CP123"}}
        
        transformed_data = await coupang_uploader.transform_product(sample_product)
        result = await coupang_uploader.upload_single(transformed_data)
        
        assert result["success"] is True
        assert result["product_id"] == "CP123"
        mock_api_request.assert_called_once()

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_single_failure(self, mock_api_request, coupang_uploader, sample_product):
        """단일 상품 업로드 실패 테스트"""
        mock_api_request.return_value = {"code": "FAILED", "message": "API Error"}
        
        transformed_data = await coupang_uploader.transform_product(sample_product)
        result = await coupang_uploader.upload_single(transformed_data)
        
        assert result["success"] is False
        assert "API Error" in result["error"]

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_update_single_success(self, mock_api_request, coupang_uploader, sample_product):
        """단일 상품 수정 성공 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS"}
        
        transformed_data = await coupang_uploader.transform_product(sample_product)
        result = await coupang_uploader.update_single("CP123", transformed_data)
        
        assert result["success"] is True
        assert result["product_id"] == "CP123"

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_check_product_status_success(self, mock_api_request, coupang_uploader):
        """상품 상태 확인 성공 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS", "data": {"status": "APPROVED"}}
        
        result = await coupang_uploader.check_product_status("CP123")
        
        assert result["success"] is True
        assert result["status"] == "APPROVED"

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_product_new(self, mock_api_request, coupang_uploader, sample_product, mock_storage):
        """새 상품 업로드 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS", "data": {"productId": "NEW_CP456"}}
        mock_storage.get_marketplace_upload.return_value = None # 기존 업로드 없음
        
        result = await coupang_uploader.upload_product(sample_product, update_existing=False)
        
        assert result["status"] == UploadStatus.SUCCESS
        assert result["marketplace_product_id"] == "NEW_CP456"
        assert coupang_uploader.stats["uploaded"] == 1
        mock_storage.save_marketplace_upload.assert_called_once()

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_product_update_existing(self, mock_api_request, coupang_uploader, sample_product, mock_storage):
        """기존 상품 업데이트 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS"}
        mock_storage.get_marketplace_upload.return_value = {"marketplace_product_id": "EXISTING_CP789"} # 기존 업로드 있음
        
        result = await coupang_uploader.upload_product(sample_product, update_existing=True)
        
        assert result["status"] == UploadStatus.SUCCESS
        assert result["marketplace_product_id"] == "EXISTING_CP789"
        assert coupang_uploader.stats["uploaded"] == 1
        mock_storage.save_marketplace_upload.assert_called_once()

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_product_validation_failure(self, mock_api_request, coupang_uploader, sample_product):
        """상품 검증 실패 시 업로드 테스트"""
        sample_product.name = "" # 검증 실패 유도
        
        result = await coupang_uploader.upload_product(sample_product)
        
        assert result["status"] == UploadStatus.FAILED
        assert "검증 실패" in result["errors"][0]
        assert coupang_uploader.stats["failed"] == 1
        mock_api_request.assert_not_called()

    @pytest.mark.asyncio
    @patch('dropshipping.uploader.coupang_api.uploader.CoupangUploader._api_request')
    async def test_upload_batch(self, mock_api_request, coupang_uploader, sample_product, mock_storage):
        """배치 업로드 테스트"""
        mock_api_request.return_value = {"code": "SUCCESS", "data": {"productId": "CP_BATCH"}}
        mock_storage.get_marketplace_upload.return_value = None

        products_to_upload = [sample_product, sample_product, sample_product]
        results = await coupang_uploader.upload_batch(products_to_upload)

        assert len(results) == 3
        assert all(r["status"] == UploadStatus.SUCCESS for r in results)
        assert coupang_uploader.stats["uploaded"] == 3
        assert mock_api_request.call_count == 3
        assert mock_storage.save_marketplace_upload.call_count == 3
