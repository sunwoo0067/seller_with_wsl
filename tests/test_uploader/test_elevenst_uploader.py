import pytest
from unittest.mock import MagicMock, AsyncMock

from dropshipping.config import ElevenstConfig
from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.elevenst_api.elevenst_uploader import ElevenstUploader
from dropshipping.uploader.registry import UploaderRegistry

@pytest.fixture
def mock_storage():
    """Mock BaseStorage."""
    return MagicMock(spec=BaseStorage)

@pytest.fixture
def elevenst_config():
    """Fixture for ElevenstConfig with test values."""
    return ElevenstConfig(
        api_key="test_api_key",
        seller_id="test_seller_id",
        test_mode=True,
    )

@pytest.fixture
def uploader_registry():
    """Fixture for UploaderRegistry with ElevenstUploader registered."""
    registry = UploaderRegistry()
    registry.register("elevenst", ElevenstUploader)
    return registry

@pytest.mark.asyncio
async def test_get_uploader_with_dependency_injection(
    uploader_registry: UploaderRegistry,
    mock_storage: BaseStorage,
    elevenst_config: ElevenstConfig,
):
    """
    Test if UploaderRegistry correctly injects dependencies (storage, config)
    when creating an uploader instance.
    """
    uploader = uploader_registry.get_uploader(
        name="elevenst", storage=mock_storage, config=elevenst_config
    )

    assert isinstance(uploader, ElevenstUploader)
    assert uploader.storage is mock_storage
    assert uploader.config is elevenst_config
    assert uploader.seller_id == "test_seller_id"
    assert uploader.test_mode is True

@pytest.mark.asyncio
async def test_elevenst_uploader_uses_config_values(
    mock_storage: BaseStorage, elevenst_config: ElevenstConfig
):
    """
    Test if ElevenstUploader correctly uses values from the config object.
    """
    uploader = ElevenstUploader(storage=mock_storage, config=elevenst_config)
    uploader._api_request = AsyncMock(return_value={"ResultCode": "Success"})

    product = StandardProduct(
        id="P002",
        supplier_id="S002",
        supplier_product_id="SP002",
        name="Test 11st Product",
        price=25000,
        cost=15000,
        stock=20,
        category_name="의류/여성의류",
        images=[],
        description="<p>11st Test Description</p>"
    )

    product_data = await uploader.transform_product(product)

    assert product_data["Product"]["dispCtgrNo"] == elevenst_config.category_mapping["의류/여성의류"]
    assert product_data["Product"]["dlvCst1"] == str(elevenst_config.delivery_cost)

    # This test is simplified and doesn't call upload_single because it requires complex XML handling.
    # The main purpose is to check if config values are correctly used during transformation.
    assert True
