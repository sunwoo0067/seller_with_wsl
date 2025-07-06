"""
오너클랜 공급사 통합 테스트
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from dropshipping.suppliers.ownerclan.fetcher import OwnerclanFetcher
from dropshipping.suppliers.ownerclan.parser import OwnerclanParser
from dropshipping.suppliers.ownerclan.transformer import OwnerclanTransformer
from dropshipping.models.product import StandardProduct, ProductStatus


@pytest.fixture
def mock_storage():
    """Mock storage"""
    storage = Mock()
    storage.save_raw_products = Mock(return_value=None)
    storage.save_processed_products = Mock(return_value=None)
    return storage


@pytest.fixture
def ownerclan_fetcher(mock_storage):
    """Ownerclan fetcher fixture"""
    return OwnerclanFetcher(
        storage=mock_storage,
        supplier_name="ownerclan",
        username="test_user",
        password="test_pass",
        api_url="https://api.ownerclan.com/v1/graphql",
    )


@pytest.fixture
def sample_auth_response():
    """샘플 인증 응답"""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"


@pytest.fixture
def sample_list_response():
    """샘플 상품 목록 응답"""
    return {
        "data": {
            "allItems": {
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor123"},
                "edges": [
                    {
                        "node": {
                            "key": "ITEM001",
                            "name": "테스트 상품 1",
                            "price": 10000,
                            "status": "AVAILABLE",
                        }
                    },
                    {
                        "node": {
                            "key": "ITEM002",
                            "name": "테스트 상품 2",
                            "price": 20000,
                            "status": "AVAILABLE",
                        }
                    },
                ],
            }
        }
    }


@pytest.fixture
def sample_detail_response():
    """샘플 상품 상세 응답"""
    return {
        "data": {
            "item": {
                "key": "ITEM001",
                "name": "테스트 상품 1",
                "model": "TEST-001",
                "production": "테스트 제조사",
                "origin": "대한민국",
                "price": 10000,
                "fixedPrice": 12000,
                "category": {"name": "의류/패션"},
                "shippingFee": 3000,
                "shippingType": "PAID",
                "status": "AVAILABLE",
                "options": [
                    {
                        "price": 10000,
                        "quantity": 50,
                        "optionAttributes": [
                            {"name": "색상", "value": "블랙"},
                            {"name": "사이즈", "value": "M"},
                        ],
                    },
                    {
                        "price": 10000,
                        "quantity": 30,
                        "optionAttributes": [
                            {"name": "색상", "value": "블랙"},
                            {"name": "사이즈", "value": "L"},
                        ],
                    },
                ],
                "taxFree": False,
                "adultOnly": False,
                "returnable": True,
                "images": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-02T00:00:00Z",
            }
        }
    }


class TestOwnerclanFetcher:
    """Ownerclan Fetcher 테스트"""

    def test_get_token(self, ownerclan_fetcher, sample_auth_response):
        """토큰 획득 테스트"""
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.text = sample_auth_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            token = ownerclan_fetcher._get_token()

            assert token == sample_auth_response
            assert ownerclan_fetcher.token == sample_auth_response
            mock_post.assert_called_once_with(
                "https://auth.ownerclan.com/auth",
                json={
                    "service": "ownerclan",
                    "userType": "seller",
                    "username": "test_user",
                    "password": "test_pass",
                },
                timeout=30,
            )

    def test_call_api_with_auth(self, ownerclan_fetcher, sample_list_response):
        """API 호출 테스트 (인증 포함)"""
        with patch("requests.post") as mock_post:
            # 첫 번째 호출: 인증
            auth_response = Mock()
            auth_response.text = "test.token"
            auth_response.raise_for_status = Mock()

            # 두 번째 호출: API
            api_response = Mock()
            api_response.status_code = 200
            api_response.json.return_value = sample_list_response
            api_response.raise_for_status = Mock()

            mock_post.side_effect = [auth_response, api_response]

            result = ownerclan_fetcher._call_api("query { test }")

            assert result == sample_list_response
            assert mock_post.call_count == 2

    def test_fetch_list(self, ownerclan_fetcher, sample_list_response):
        """상품 목록 조회 테스트"""
        with patch.object(ownerclan_fetcher, "_call_api", return_value=sample_list_response):
            products = ownerclan_fetcher.fetch_list(1)

            assert len(products) == 2
            assert products[0]["key"] == "ITEM001"
            assert products[1]["key"] == "ITEM002"

    def test_fetch_detail(self, ownerclan_fetcher, sample_detail_response):
        """상품 상세 조회 테스트"""
        with patch.object(ownerclan_fetcher, "_call_api", return_value=sample_detail_response):
            product = ownerclan_fetcher.fetch_detail("ITEM001")

            assert product["key"] == "ITEM001"
            assert product["name"] == "테스트 상품 1"
            assert len(product["options"]) == 2


class TestOwnerclanParser:
    """Ownerclan Parser 테스트"""

    def test_parse_products(self, sample_list_response):
        """상품 목록 파싱 테스트"""
        parser = OwnerclanParser()
        products = parser.parse_products(sample_list_response)

        assert len(products) == 2
        assert products[0]["id"] == "ITEM001"
        assert products[0]["name"] == "테스트 상품 1"
        assert products[0]["price"] == 10000

    def test_parse_product_detail(self, sample_detail_response):
        """상품 상세 파싱 테스트"""
        parser = OwnerclanParser()
        product = parser.parse_product_detail(sample_detail_response)

        assert product["id"] == "ITEM001"
        assert product["brand"] == "테스트 제조사"
        assert product["category"] == "의류/패션"
        assert len(product["options"]) == 2
        assert product["options"][0]["name"] == "색상: 블랙, 사이즈: M"
        assert product["stock"] == 80  # 50 + 30

    def test_parse_error(self):
        """에러 파싱 테스트"""
        parser = OwnerclanParser()
        error_response = {"errors": [{"message": "Authentication failed"}]}

        error_msg = parser.parse_error(error_response)
        assert error_msg == "Authentication failed"


class TestOwnerclanTransformer:
    """Ownerclan Transformer 테스트"""

    def test_transform_basic(self, sample_detail_response):
        """기본 변환 테스트"""
        parser = OwnerclanParser()
        parsed = parser.parse_product_detail(sample_detail_response)

        transformer = OwnerclanTransformer()
        product = transformer.transform(parsed)

        assert isinstance(product, StandardProduct)
        assert product.supplier_id == "ownerclan"
        assert product.supplier_product_id == "ITEM001"
        assert product.name == "테스트 상품 1"
        assert product.brand == "테스트 제조사"
        assert float(product.cost) == 10000
        assert float(product.price) == 13000  # 10000 * 1.3
        assert len(product.images) == 2
        assert product.status == ProductStatus.ACTIVE

    def test_transform_options(self, sample_detail_response):
        """옵션 변환 테스트"""
        parser = OwnerclanParser()
        parsed = parser.parse_product_detail(sample_detail_response)

        transformer = OwnerclanTransformer()
        product = transformer.transform(parsed)

        assert len(product.options) == 2  # 색상, 사이즈
        assert product.options[0].name in ["색상", "사이즈"]
        assert len(product.variants) == 2
        assert product.variants[0].stock == 50
        assert product.stock == 80

    def test_transform_shipping(self, sample_detail_response):
        """배송 정보 변환 테스트"""
        parser = OwnerclanParser()
        parsed = parser.parse_product_detail(sample_detail_response)

        transformer = OwnerclanTransformer()
        product = transformer.transform(parsed)

        assert product.shipping_method == "유료배송"
        assert float(product.shipping_fee) == 3000
        # shipping_info는 attributes에 저장됨
        shipping_info = product.attributes.get("shipping_info", {})
        assert shipping_info.get("estimated_days_min") == 2
        assert shipping_info.get("estimated_days_max") == 3

    def test_transform_invalid_product(self):
        """잘못된 상품 변환 테스트"""
        transformer = OwnerclanTransformer()

        # 필수 필드 누락
        invalid_product = {"name": "테스트"}
        result = transformer.transform(invalid_product)
        assert result is None

        # 빈 상품
        result = transformer.transform({})
        assert result is None


@pytest.mark.integration
class TestOwnerclanIntegration:
    """오너클랜 통합 테스트"""

    def test_full_pipeline(
        self, mock_storage, sample_auth_response, sample_list_response, sample_detail_response
    ):
        """전체 파이프라인 테스트"""
        with patch("requests.post") as mock_post:
            # 인증 응답 설정
            auth_response = Mock()
            auth_response.text = sample_auth_response
            auth_response.raise_for_status = Mock()

            # API 응답 설정
            list_response = Mock()
            list_response.status_code = 200
            list_response.json.return_value = sample_list_response
            list_response.raise_for_status = Mock()

            detail_response = Mock()
            detail_response.status_code = 200
            detail_response.json.return_value = sample_detail_response
            detail_response.raise_for_status = Mock()

            mock_post.side_effect = [auth_response, list_response, detail_response]

            # Fetcher 초기화
            fetcher = OwnerclanFetcher(
                storage=mock_storage,
                supplier_name="ownerclan",
                username="test_user",
                password="test_pass",
                api_url="https://api.ownerclan.com/v1/graphql",
            )

            # Parser와 Transformer
            parser = OwnerclanParser()
            transformer = OwnerclanTransformer()

            # 상품 목록 조회
            products = fetcher.fetch_list(1)
            parsed_products = parser.parse_products(
                {"data": {"allItems": {"edges": [{"node": p} for p in products]}}}
            )

            # 첫 번째 상품 상세 조회 및 변환
            detail = fetcher.fetch_detail(parsed_products[0]["id"])
            parsed_detail = parser.parse_product_detail({"data": {"item": detail}})
            standard_product = transformer.transform(parsed_detail)

            # 검증
            assert standard_product is not None
            assert standard_product.supplier_id == "ownerclan"
            assert standard_product.supplier_product_id == "ITEM001"
            assert standard_product.name == "테스트 상품 1"
            assert len(standard_product.options) == 2
            assert standard_product.stock == 80
