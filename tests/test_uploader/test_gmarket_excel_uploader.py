"""
G마켓/옥션 Excel 업로더 테스트
"""

import pytest
from unittest.mock import MagicMock
from pathlib import Path
from decimal import Decimal

from dropshipping.config import GmarketUploaderConfig
from dropshipping.models.product import StandardProduct, ProductVariant, ProductImage
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import MarketplaceType
from dropshipping.uploader.gmarket_excel.gmarket_excel_uploader import GmarketExcelUploader


@pytest.fixture
def mock_storage():
    """Mock BaseStorage."""
    return MagicMock(spec=BaseStorage)


@pytest.fixture
def gmarket_config():
    """Fixture for GmarketUploaderConfig with test values."""
    return GmarketUploaderConfig(
        output_dir="/tmp/gmarket_test",
        seller_code="test_seller",
        shipping_address="test_shipping_address",
        return_address="test_return_address",
        category_mapping={"전자기기/이어폰": "200001541"},  # Add mapping for the test
    )


@pytest.fixture
def sample_product():
    """Fixture for a sample StandardProduct."""
    return StandardProduct(
        id="12345",
        supplier_id="S001",
        supplier_product_id="P001",
        name="Test Product",
        description="<p>Test Description</p>",
        category_name="전자기기/이어폰",
        cost=Decimal("8000"),
        price=Decimal("10000"),
        images=[
            ProductImage(url="http://example.com/image1.jpg", is_main=True),
            ProductImage(url="http://example.com/image2.jpg"),
        ],
        variants=[
            ProductVariant(sku="P001-R", options={"Color": "Red"}, stock=10),
            ProductVariant(sku="P001-B", options={"Color": "Blue"}, stock=20),
        ],
    )


@pytest.mark.parametrize(
    "marketplace_type",
    [MarketplaceType.GMARKET, MarketplaceType.AUCTION],
)
def test_gmarket_excel_uploader_initialization(
    mock_storage: BaseStorage,
    gmarket_config: GmarketUploaderConfig,
    marketplace_type: MarketplaceType,
):
    """Test GmarketExcelUploader initialization for both Gmarket and Auction."""
    uploader = GmarketExcelUploader(
        storage=mock_storage, config=gmarket_config, marketplace_type=marketplace_type
    )

    assert uploader.storage is mock_storage
    assert uploader.config is gmarket_config
    assert uploader.marketplace_type == marketplace_type
    assert uploader.seller_code == "test_seller"
    assert uploader.output_dir == Path("/tmp/gmarket_test")


async def test_transform_product(gmarket_config, sample_product):
    """Test the transformation of a StandardProduct to the Excel data format."""
    uploader = GmarketExcelUploader(
        storage=MagicMock(), config=gmarket_config, marketplace_type=MarketplaceType.GMARKET
    )

    excel_data = await uploader.transform_product(sample_product)

    assert excel_data["판매가"] == 10000
    assert excel_data["상품명"] == "Test Product"
    assert excel_data["카테고리코드"] == "200001541"
    assert "<p>Test Description</p>" in excel_data["상품상세설명"]
    assert excel_data["상품이미지1"] == "http://example.com/image1.jpg"
    assert excel_data["옵션사용여부"] == "Y"
    assert excel_data["옵션명"] == "Color"
    assert excel_data["옵션값"] == "Red,Blue"
    assert excel_data["옵션재고"] == "10,20"
    assert excel_data["판매자상품코드"] == "12345"  # Uses product.id


async def test_upload_product_not_implemented(gmarket_config, sample_product):
    """Test that upload_product raises NotImplementedError."""
    uploader = GmarketExcelUploader(
        storage=MagicMock(), config=gmarket_config, marketplace_type=MarketplaceType.GMARKET
    )
    with pytest.raises(NotImplementedError):
        await uploader.upload_product(sample_product)


async def test_upload_products_in_batch_not_implemented(gmarket_config, sample_product):
    """Test that upload_products_in_batch raises NotImplementedError."""
    uploader = GmarketExcelUploader(
        storage=MagicMock(), config=gmarket_config, marketplace_type=MarketplaceType.GMARKET
    )
    with pytest.raises(NotImplementedError):
        await uploader.upload_products_in_batch([sample_product])
