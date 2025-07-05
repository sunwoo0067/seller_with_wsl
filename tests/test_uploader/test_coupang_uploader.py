"""
쿠팡 업로더 테스트
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dropshipping.models.product import ProductImage, ProductVariant, StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.coupang_api.coupang_uploader import CoupangUploader


class TestCoupangUploader:
    """CoupangUploader 테스트"""

    @pytest.fixture
    def mock_storage(self):
        """Mock 저장소"""
        return Mock(spec=BaseStorage)

    @pytest.fixture
    def uploader(self, mock_storage):
        """테스트용 쿠팡 업로더"""
        config = {
            "api_key": "test_access_key",
            "api_secret": "test_secret_key",
            "vendor_id": "A00000000",
            "test_mode": True,
            "return_center_code": "1000274592",
            "shipping_place_code": "74010",
        }
        return CoupangUploader(storage=mock_storage, config=config)

    @pytest.fixture
    def sample_product(self):
        """테스트용 상품"""
        return StandardProduct(
            id="cp-test-001",
            supplier_id="domeme",
            supplier_product_id="DM001",
            name="[테스트] 블루투스 이어폰 TWS 무선 충전 케이스 포함",
            description="고품질 블루투스 5.0 이어폰",
            price=29900,
            cost=15000,
            category_name="전자기기/이어폰",
            stock=100,
            brand="TestBrand",
            images=[
                ProductImage(url="https://example.com/main.jpg", is_main=True),
                ProductImage(url="https://example.com/sub1.jpg", is_main=False),
            ],
            attributes={"shipping_fee": 2500, "model": "TWS-001", "manufacturer": "테스트 제조사"},
        )

    def test_init(self, uploader):
        """초기화 테스트"""
        assert uploader.vendor_id == "A00000000"
        assert uploader.test_mode is True
        assert uploader.base_url == "https://api-gateway-it.coupang.com"
        assert "전자기기/이어폰" in uploader.category_mapping

    def test_validate_product_success(self, uploader, sample_product):
        """상품 검증 성공 테스트"""
        is_valid, error = asyncio.run(uploader.validate_product(sample_product))

        assert is_valid is True
        assert error is None

    def test_validate_product_fail(self, uploader):
        """상품 검증 실패 테스트"""
        invalid_product = StandardProduct(
            id="invalid-001",
            supplier_id="test",
            supplier_product_id="TEST001",
            name="",  # 빈 상품명
            price=50,  # 너무 낮은 가격
            cost=30,
            category_name="미지원카테고리",
            stock=0,
            images=[],  # 이미지 없음
        )

        is_valid, error = asyncio.run(uploader.validate_product(invalid_product))

        assert is_valid is False
        assert "상품명 누락" in error
        assert "판매가격이 너무 낮습니다" in error
        assert "상품 이미지가 없습니다" in error
        assert "지원하지 않는 카테고리" in error

    def test_transform_product(self, uploader, sample_product):
        """상품 변환 테스트"""
        coupang_data = asyncio.run(uploader.transform_product(sample_product))

        assert coupang_data["displayCategoryCode"] == "1001"
        assert coupang_data["sellerProductName"] == sample_product.name
        assert coupang_data["vendorId"] == "A00000000"
        assert coupang_data["brand"] == "TestBrand"
        assert coupang_data["deliveryCharge"] == 2500
        assert len(coupang_data["images"]) == 2
        assert coupang_data["images"][0]["imageType"] == "REPRESENTATION"
        assert coupang_data["images"][1]["imageType"] == "DETAIL"
        assert len(coupang_data["items"]) == 1
        assert coupang_data["sellerProductId"] == "cp-test-001"

    def test_transform_product_with_variants(self, uploader):
        """옵션이 있는 상품 변환 테스트"""
        product_with_variants = StandardProduct(
            id="cp-test-002",
            supplier_id="domeme",
            supplier_product_id="DM002",
            name="테스트 티셔츠",
            price=19900,
            cost=10000,
            category_name="의류/여성의류",
            stock=100,
            variants=[
                ProductVariant(
                    sku="cp-test-002-S",
                    options={"사이즈": "S"},
                    price=19900,
                    stock=30,
                    barcode="1234567890123",
                ),
                ProductVariant(sku="cp-test-002-M", options={"사이즈": "M"}, price=19900, stock=40),
                ProductVariant(sku="cp-test-002-L", options={"사이즈": "L"}, price=19900, stock=30),
            ],
        )

        coupang_data = asyncio.run(uploader.transform_product(product_with_variants))

        items = coupang_data["items"]
        assert len(items) == 3
        assert items[0]["itemName"] == "S"  # 옵션값이 itemName이 됨
        assert items[0]["externalVendorSku"] == "cp-test-002-S"
        assert items[0]["barcode"] == "1234567890123"
        assert items[1]["emptyBarcode"] is True

    def test_create_auth_headers(self, uploader):
        """인증 헤더 생성 테스트"""
        headers = uploader._create_auth_headers(
            "GET",
            "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products",
            {"vendorId": "A00000000"},
        )

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("CEA algorithm=HmacSHA256")
        assert "access-key=test_access_key" in headers["Authorization"]
        assert headers["X-Requested-By"] == "A00000000"
        assert headers["Content-Type"] == "application/json;charset=UTF-8"

    def test_upload_single_success(self, uploader):
        """단일 상품 업로드 성공 테스트"""
        mock_response = {
            "code": "SUCCESS",
            "message": "상품 등록 성공",
            "data": {"productId": "1234567890"},
        }

        with patch.object(uploader, "_api_request", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = asyncio.run(uploader.upload_single({"test": "data"}))

        assert result["success"] is True
        assert result["product_id"] == "1234567890"
        assert result["message"] == "상품 등록 성공"

    def test_upload_single_fail(self, uploader):
        """단일 상품 업로드 실패 테스트"""
        mock_response = {"code": "ERROR", "message": "필수 항목이 누락되었습니다"}

        with patch.object(uploader, "_api_request", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = asyncio.run(uploader.upload_single({"test": "data"}))

        assert result["success"] is False
        assert result["error"] == "필수 항목이 누락되었습니다"
        assert result["code"] == "ERROR"

    def test_update_single(self, uploader):
        """상품 수정 테스트"""
        mock_response = {"code": "SUCCESS", "message": "상품 수정 성공"}

        with patch.object(uploader, "_api_request", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = asyncio.run(uploader.update_single("1234567890", {"test": "data"}))

        assert result["success"] is True
        assert result["product_id"] == "1234567890"

        # API 호출 시 productId가 추가되었는지 확인
        call_args = mock_api.call_args
        assert call_args[1]["json"]["productId"] == "1234567890"

    def test_check_product_status(self, uploader):
        """상품 상태 확인 테스트"""
        mock_response = {
            "code": "SUCCESS",
            "data": {"status": "APPROVED", "statusName": "승인완료"},
        }

        with patch.object(uploader, "_api_request", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = asyncio.run(uploader.check_product_status("1234567890"))

        assert result["success"] is True
        assert result["status"] == "APPROVED"
        assert result["status_name"] == "승인완료"

    def test_close(self, uploader):
        """HTTP 클라이언트 종료 테스트"""
        with patch.object(uploader.client, "aclose", new_callable=AsyncMock) as mock_close:
            asyncio.run(uploader.close())
            mock_close.assert_called_once()
