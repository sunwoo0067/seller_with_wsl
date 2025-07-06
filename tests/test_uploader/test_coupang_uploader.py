import pytest
from unittest.mock import MagicMock, AsyncMock

from dropshipping.config import CoupangConfig
from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.coupang_api.coupang_uploader import CoupangUploader
from dropshipping.uploader.registry import UploaderRegistry


@pytest.fixture
def mock_storage():
    """Mock BaseStorage."""
    return MagicMock(spec=BaseStorage)


@pytest.fixture
def coupang_config():
    """Fixture for CoupangConfig with test values."""
    return CoupangConfig(
        access_key="test_access_key",
        secret_key="test_secret_key",
        vendor_id="test_vendor_id",
        test_mode=True,
    )


@pytest.fixture
def uploader_registry():
    """Fixture for UploaderRegistry with CoupangUploader registered."""
    registry = UploaderRegistry()
    registry.register("coupang", CoupangUploader)
    return registry


@pytest.mark.asyncio
async def test_get_uploader_with_dependency_injection(
    uploader_registry: UploaderRegistry,
    mock_storage: BaseStorage,
    coupang_config: CoupangConfig,
):
    """
    Test if UploaderRegistry correctly injects dependencies (storage, config)
    when creating an uploader instance.
    """
    # Get the uploader from the registry
    uploader = uploader_registry.get_uploader(
        name="coupang", storage=mock_storage, config=coupang_config
    )

    # Assert that the uploader is an instance of CoupangUploader
    assert isinstance(uploader, CoupangUploader)

    # Assert that the storage and config objects are correctly assigned
    assert uploader.storage is mock_storage
    assert uploader.config is coupang_config
    assert uploader.vendor_id == "test_vendor_id"
    assert uploader.test_mode is True
    assert uploader.base_url == "https://api-gateway-it.coupang.com"


@pytest.mark.asyncio
async def test_coupang_uploader_uses_config_values(
    mock_storage: BaseStorage, coupang_config: CoupangConfig
):
    """
    Test if CoupangUploader correctly uses values from the config object.
    """
    # Instantiate the uploader directly
    uploader = CoupangUploader(storage=mock_storage, config=coupang_config)

    # Mock the internal _api_request method
    uploader._api_request = AsyncMock(
        return_value={"code": "SUCCESS", "data": {"sellerProductId": "12345"}}
    )

    # Create a dummy product
    product = StandardProduct(
        id="P001",
        supplier_id="S001",
        supplier_product_id="SP001",
        name="Test Product",
        price=15000,
        cost=10000,
        stock=10,
        category_name="전자기기/이어폰",  # A category present in the default mapping
        images=[],
        description="<p>Test Description</p>",
    )

    # Transform the product
    product_data = await uploader.transform_product(product)

    # Check if values from config are used in the transformed data
    assert product_data["vendorId"] == "test_vendor_id"
    assert product_data["returnCenterCode"] == coupang_config.return_center_code
    assert product_data["deliveryCompanyCode"] == coupang_config.delivery_company_code
    assert product_data["freeShipOverAmount"] == coupang_config.free_ship_over_amount

    # Call the upload method
    result = await uploader.upload_single(product_data)

    # Assert the result
    assert result["status"] == "uploaded"
    assert result["marketplace_product_id"] is not None

    # Assert that _api_request was called with the correct data
    uploader._api_request.assert_called_once()
    call_args = uploader._api_request.call_args
    assert call_args.args[0] == "POST"
    assert call_args.kwargs["json"]["vendorId"] == "test_vendor_id"
