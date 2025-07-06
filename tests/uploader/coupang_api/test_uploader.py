import pytest
from unittest.mock import Mock, patch
import requests
from decimal import Decimal

from dropshipping.uploader.coupang_api.uploader import CoupangUploader
from dropshipping.models.product import StandardProduct, ProductStatus
from dropshipping.config import settings

@pytest.fixture
def mock_coupang_settings():
    """쿠팡 API 키 설정을 Mock"""
    with patch('dropshipping.config.CoupangConfig') as MockCoupangConfig:
        mock_coupang_instance = Mock()
        mock_coupang_instance.access_key = "test_access_key"
        mock_coupang_instance.secret_key = "test_secret_key"
        mock_coupang_instance.vendor_id = "test_vendor_id"
        MockCoupangConfig.return_value = mock_coupang_instance
        yield

@pytest.fixture
def coupang_uploader(mock_coupang_settings):
    """CoupangUploader 인스턴스 픽스처"""
    mock_session = Mock(spec=requests.Session)
    uploader = CoupangUploader(marketplace_id="coupang_mp_id", account_id="coupang_acc_id", session=mock_session)
    return uploader

@pytest.fixture
def mock_requests_methods(mocker):
    """requests.Session의 post, put, get을 Mock"""
    mock_session = mocker.Mock(spec=requests.Session)
    mock_post = mocker.patch.object(mock_session, 'post')
    mock_put = mocker.patch.object(mock_session, 'put')
    mock_get = mocker.patch.object(mock_session, 'get')

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "SUCCESS", "message": "성공", "data": {"sellerProductId": "CP123"}}
    mock_response.raise_for_status = Mock() # 에러 발생 방지

    mock_post.return_value = mock_response
    mock_put.return_value = mock_response
    mock_get.return_value = mock_response

    # Return only the mocks for post, put, get
    return mock_post, mock_put, mock_get

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
        category_code="C100",
        category_name="의류",
        category_path=["패션", "의류"],
        images=[],
        options=[],
        attributes={}
    )

def test_upload_product_success(coupang_uploader, mock_requests_methods, sample_standard_product):
    """상품 업로드 성공 테스트"""
    mock_post, _, _ = mock_requests_methods # Correct
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": "SUCCESS",
        "message": "성공",
        "data": {"sellerProductId": "CP123"}
    }
    mock_post.return_value = mock_response

    result = coupang_uploader.upload_product(sample_standard_product)

    assert result['status'] == 'uploaded'
    assert result['marketplace_product_id'] == 'CP123'
    assert 'coupang.com' in result['marketplace_url']
    mock_post.assert_called_once()

def test_upload_product_failure(coupang_uploader, mock_requests_methods, sample_standard_product):
    """상품 업로드 실패 테스트"""
    mock_post, _, _ = mock_requests_methods # Correct
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "code": "ERROR",
        "message": "잘못된 요청"
    }
    mock_post.return_value = mock_response

    result = coupang_uploader.upload_product(sample_standard_product)

    assert result['status'] == 'failed'
    assert result['error'] == '잘못된 요청'

def test_update_stock_success(coupang_uploader, mock_requests_methods):
    """재고 업데이트 성공 테스트"""
    _, mock_put, _ = mock_requests_methods # Correct
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "SUCCESS"}
    mock_put.return_value = mock_response

    result = coupang_uploader.update_stock('CP123', 50)

    assert result is True
    mock_put.assert_called_once()

def test_update_stock_failure(coupang_uploader, mock_requests_methods):
    """재고 업데이트 실패 테스트"""
    _, mock_put, _ = mock_requests_methods # Correct
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"code": "ERROR"}
    mock_put.return_value = mock_response

    result = coupang_uploader.update_stock('CP123', 50)

    assert result is False

def test_update_price_success(coupang_uploader, mock_requests_methods):
    """가격 업데이트 성공 테스트"""
    _, mock_put, _, _ = mock_requests_methods
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "SUCCESS"}
    mock_put.return_value = mock_response

    result = coupang_uploader.update_price('CP123', 16000.0)

    assert result is True
    mock_put.assert_called_once()

def test_update_price_failure(coupang_uploader, mock_requests_methods):
    """가격 업데이트 실패 테스트"""
    _, mock_put, _, _ = mock_requests_methods
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"code": "ERROR"}
    mock_put.return_value = mock_response

    result = coupang_uploader.update_price('CP123', 16000.0)

    assert result is False

def test_check_upload_status(coupang_uploader):
    """업로드 상태 확인 테스트"""
    status = coupang_uploader.check_upload_status('upload_id_123')
    assert status['status'] == 'completed'
    assert 'message' in status