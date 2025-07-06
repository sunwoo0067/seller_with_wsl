import pytest
from unittest.mock import Mock
import respx
import httpx
from decimal import Decimal

from dropshipping.uploader.coupang_api.coupang_uploader import CoupangUploader
from dropshipping.models.product import StandardProduct, ProductStatus, ProductImage
from dropshipping.config import CoupangConfig
from dropshipping.storage.base import BaseStorage


@pytest.fixture
def coupang_config(tmp_path) -> CoupangConfig:
    """CoupangConfig 픽스처"""
    return CoupangConfig(
        access_key="test_access_key",
        secret_key="test_secret_key",
        vendor_id="test_vendor_id",
        test_mode=True,
        category_mapping={"의류": "513"}, # 예: 의류 -> 여성의류
    )

@pytest.fixture
def coupang_uploader(coupang_config):
    """CoupangUploader 인스턴스 픽스처"""
    mock_storage = Mock(spec=BaseStorage)
    uploader = CoupangUploader(storage=mock_storage, config=coupang_config)
    return uploader

@pytest.fixture
def sample_standard_product():
    """샘플 StandardProduct 인스턴스"""
    return StandardProduct(
        id="prod_uuid_123",
        supplier_id="domeme",
        supplier_product_id="SP123",
        name="테스트 상품",
        brand="테스트 브랜드",
        manufacturer="테스트 제조사",
        origin="한국",
        cost=Decimal('10000'),
        price=Decimal('15000'),
        list_price=Decimal('20000'),
        stock=100,
        status=ProductStatus.ACTIVE,
        category_name="의류",
        category_path=["패션", "의류"],
        images=[ProductImage(url="http://example.com/image.jpg", is_main=True)],
        options=[],
        attributes={}
    )


@respx.mock
async def test_upload_product_success(coupang_uploader, sample_standard_product):
    """상품 업로드 성공 테스트"""
    # Given
    respx.post("https://api-gateway-it.coupang.com/v2/providers/seller_api/v1/products").mock(
        return_value=httpx.Response(
            200, json={"code": "SUCCESS", "data": {"sellerProductId": "test_product_123"}}
        )
    )

    # When
    result = await coupang_uploader.upload_product(sample_standard_product)

    # Then
    assert result["status"] == "uploaded"
    assert result["marketplace_product_id"] == "test_product_123"
    assert 'coupang.com' in result['marketplace_url']
    assert respx.calls.call_count == 1


async def test_upload_product_failure_on_validation(coupang_uploader, sample_standard_product):
    """상품 업로드 실패 테스트 (검증 오류)"""
    # Given
    sample_standard_product.category_name = "없는 카테고리" # 지원하지 않는 카테고리

    # When
    result = await coupang_uploader.upload_product(sample_standard_product)

    # Then
    assert result["status"] == "failed"
    assert "지원하지 않는 카테고리" in result["error_message"]
    assert result.get('marketplace_product_id') is None


async def test_update_stock_raises_not_implemented(coupang_uploader):
    """재고 업데이트 미구현 테스트"""
    with pytest.raises(NotImplementedError):
        await coupang_uploader.update_stock("CP123", 50)


async def test_update_price_raises_not_implemented(coupang_uploader):
    """가격 업데이트 미구현 테스트"""
    with pytest.raises(NotImplementedError):
        await coupang_uploader.update_price("CP123", Decimal("16000"))


@respx.mock
async def test_check_upload_status(coupang_uploader):
    """상품 상태 확인 테스트"""
    # Given
    marketplace_product_id = "12345"
    respx.get(f"https://api-gateway-it.coupang.com/v2/providers/seller_api/v1/products/status/{marketplace_product_id}").mock(
        return_value=httpx.Response(200, json={"code": "SUCCESS", "data": {"status": "APPROVED"}})
    )

    # When
    status = await coupang_uploader.check_upload_status(marketplace_product_id)

    # Then
    assert status == "APPROVED"