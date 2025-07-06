import pytest
from unittest.mock import MagicMock

from dropshipping.config import SmartstoreConfig
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.registry import UploaderRegistry
from dropshipping.uploader.smartstore_api.smartstore_uploader import SmartstoreUploader


@pytest.fixture
def mock_storage():
    """Mock BaseStorage."""
    return MagicMock(spec=BaseStorage)


@pytest.fixture
def smartstore_config():
    """Fixture for SmartstoreConfig with test values."""
    return SmartstoreConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        access_token="test_access_token",
        channel_id="test_channel_id",
        outbound_location_id="test_outbound_id",
        return_address="test_return_address",
        return_detail_address="test_return_detail_address",
        return_zip_code="test_return_zip_code",
        return_tel="010-1234-5678",
    )


@pytest.fixture
def uploader_registry():
    """Fixture for UploaderRegistry with SmartstoreUploader registered."""
    registry = UploaderRegistry()
    registry.register("smartstore", SmartstoreUploader)
    return registry


@pytest.mark.asyncio
async def test_get_uploader_with_dependency_injection(
    uploader_registry: UploaderRegistry,
    mock_storage: BaseStorage,
    smartstore_config: SmartstoreConfig,
):
    """
    Test if UploaderRegistry correctly injects dependencies (storage, config)
    when creating an uploader instance.
    """
    uploader = uploader_registry.get_uploader(
        name="smartstore", storage=mock_storage, config=smartstore_config
    )

    assert isinstance(uploader, SmartstoreUploader)
    assert uploader.storage is mock_storage
    assert uploader.config is smartstore_config
    assert uploader.client_id == "test_client_id"
    assert uploader.channel_id == "test_channel_id"
