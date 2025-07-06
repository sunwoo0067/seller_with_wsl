"""
도매매(Domeme) API 클라이언트 및 수집기 테스트
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from dropshipping.storage.json_storage import JSONStorage
from dropshipping.suppliers.domeme.client import DomemeAPIError, DomemeClient
from dropshipping.suppliers.domeme.fetcher import DomemeFetcher


class TestDomemeClient:
    """도매매 클라이언트 테스트"""

    @pytest.fixture
    def client(self):
        """테스트용 클라이언트"""
        return DomemeClient(api_key="test-api-key")

    @pytest.fixture
    def mock_response_xml(self):
        """모의 XML 응답"""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <errorCode>000</errorCode>
            <errorMsg>정상</errorMsg>
            <totalCount>2</totalCount>
            <products>
                <product>
                    <productNo>12345</productNo>
                    <productNm>테스트 상품 1</productNm>
                    <supplyPrice>10000</supplyPrice>
                    <salePrice>15000</salePrice>
                    <consumerPrice>20000</consumerPrice>
                    <stockQty>100</stockQty>
                    <productStatus>Y</productStatus>
                    <category1>001</category1>
                    <categoryNm1>패션의류</categoryNm1>
                    <brandNm>TestBrand</brandNm>
                    <makerNm>TestMaker</makerNm>
                    <origin>Korea</origin>
                    <mainImg>https://example.com/image1.jpg</mainImg>
                    <description>테스트 상품입니다</description>
                    <deliveryPrice>2500</deliveryPrice>
                    <regDate>20241201</regDate>
                    <modDate>20241215</modDate>
                </product>
                <product>
                    <productNo>12346</productNo>
                    <productNm>테스트 상품 2</productNm>
                    <supplyPrice>20000</supplyPrice>
                    <salePrice>30000</salePrice>
                    <consumerPrice>40000</consumerPrice>
                    <stockQty>50</stockQty>
                    <productStatus>Y</productStatus>
                    <category1>002</category1>
                    <categoryNm1>패션잡화</categoryNm1>
                    <brandNm>TestBrand2</brandNm>
                    <makerNm>TestMaker2</makerNm>
                    <origin>China</origin>
                    <mainImg>https://example.com/image2.jpg</mainImg>
                    <description>테스트 상품 2입니다</description>
                    <deliveryPrice>0</deliveryPrice>
                    <regDate>20241202</regDate>
                    <modDate>20241216</modDate>
                </product>
            </products>
        </response>"""

    @patch("requests.get")
    def test_search_products(self, mock_get, client, mock_response_xml):
        """상품 검색 테스트"""
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resultCode": "00",
            "totalCount": 2,
            "product": [
                {
                    "productNo": "12345",
                    "productNm": "테스트 상품 1",
                    "categoryCode": "001",
                    "supplyPrice": 10000.0,
                    "salePrice": 15000.0
                },
                {
                    "productNo": "67890",
                    "productNm": "테스트 상품 2",
                    "categoryCode": "001",
                    "supplyPrice": 20000.0,
                    "salePrice": 25000.0
                }
            ]
        }
        mock_get.return_value = mock_response

        # 검색 실행
        result = client.search_products(category_code="001", start_row=1, end_row=100)

        # 결과 검증
        assert result["total_count"] == 2
        assert len(result["products"]) == 2
        assert result["products"][0]["productNo"] == "12345"
        assert result["products"][0]["productNm"] == "테스트 상품 1"
        assert result["products"][0]["supplyPrice"] == 10000.0
        assert result["has_next"] is False

        # API 호출 검증
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == client.base_url
        assert "apiKey" in call_args[1]["data"]
        assert call_args[1]["data"]["categoryCode"] == "001"

    @patch("requests.get")
    def test_api_error_handling(self, mock_post, client):
        """API 오류 처리 테스트"""
        # 오류 응답 설정
        error_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <errorCode>401</errorCode>
            <errorMsg>인증 실패</errorMsg>
        </response>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = error_xml.encode("utf-8")
        mock_get.return_value = mock_response

        # RetryError가 발생하고 내부에 DomemeAPIError가 포함됨
        from tenacity import RetryError

        with pytest.raises(RetryError) as exc_info:
            client._request({"test": "param"})

        # 내부 예외가 DomemeAPIError인지 확인
        assert isinstance(exc_info.value.last_attempt.exception(), DomemeAPIError)
        assert "401" in str(exc_info.value.last_attempt.exception())
        assert "인증 실패" in str(exc_info.value.last_attempt.exception())

    @patch("requests.get")
    def test_network_error_handling(self, mock_post, client):
        """네트워크 오류 처리 테스트"""
        # 네트워크 오류 설정
        import requests
        from tenacity import RetryError

        mock_post.side_effect = requests.RequestException("Connection error")

        # 재시도 후 오류 발생 확인
        with pytest.raises(RetryError) as exc_info:
            client.search_products()

        # 재시도 확인 (3회)
        assert mock_post.call_count == 3

        # 내부 예외가 DomemeAPIError인지 확인
        assert isinstance(exc_info.value.last_attempt.exception(), DomemeAPIError)
        assert "네트워크 오류" in str(exc_info.value.last_attempt.exception())

    def test_rate_limiting(self, client):
        """Rate limiting 테스트"""
        import time

        # 첫 번째 요청 시간 기록
        client._last_request_time = time.time()

        # 즉시 두 번째 요청
        start_time = time.time()
        client._ensure_rate_limit()
        elapsed = time.time() - start_time

        # 최소 대기 시간 확인
        assert elapsed >= client._min_request_interval * 0.9  # 약간의 오차 허용


class TestDomemeFetcher:
    """도매매 수집기 테스트"""

    @pytest.fixture
    def storage(self, tmp_path):
        """테스트용 저장소"""
        return JSONStorage(base_path=str(tmp_path / "test_data"))

    @pytest.fixture
    def fetcher(self, storage):
        """테스트용 수집기"""
        with patch("dropshipping.suppliers.domeme.client.DomemeClient") as mock_client_class:
            # Mock 클라이언트 설정
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            fetcher = DomemeFetcher(
                storage=storage,
                supplier_name="domeme",
                api_key="test-api-key",
                api_url="https://test.api.com"
            )
            fetcher.client = mock_client
            return fetcher

    def test_fetch_list(self, fetcher):
        """목록 조회 테스트"""
        # Mock 응답 설정
        mock_result = {
            "total_count": 2,
            "products": [
                {
                    "productNo": "12345",
                    "productNm": "테스트 상품 1",
                    "supplyPrice": 10000,
                    "modDate": "20241215",
                },
                {
                    "productNo": "12346",
                    "productNm": "테스트 상품 2",
                    "supplyPrice": 20000,
                    "modDate": "20241216",
                },
            ],
            "has_next": True,
        }
        fetcher.client.search_products.return_value = mock_result

        # 목록 조회
        products, has_next = fetcher.fetch_list(page=1, category="001")

        # 결과 검증
        assert len(products) == 2
        assert has_next is True
        assert products[0]["productNo"] == "12345"

        # API 호출 검증
        fetcher.client.search_products.assert_called_once_with(
            start_row=1,
            end_row=100,
            order_by="modDate",
            sort_type="desc",
            categoryCode="001",
        )

    def test_fetch_list_with_date_filter(self, fetcher):
        """날짜 필터링 테스트"""
        # Mock 응답 설정
        mock_result = {
            "total_count": 3,
            "products": [
                {"productNo": "12345", "modDate": "20241220"},  # 최근
                {"productNo": "12346", "modDate": "20241210"},  # 중간
                {"productNo": "12347", "modDate": "20241201"},  # 오래됨
            ],
            "has_next": False,
        }
        fetcher.client.search_products.return_value = mock_result

        # 12월 15일 이후 상품만 조회
        since = datetime(2024, 12, 15)
        products, has_next = fetcher.fetch_list(page=1, since=since)

        # 결과 검증 (1개만 필터링됨)
        assert len(products) == 1
        assert products[0]["productNo"] == "12345"

    def test_needs_detail_fetch(self, fetcher):
        """상세 조회 필요 여부 테스트"""
        # 설명과 추가 이미지가 있는 경우
        product_full = {
            "productNo": "12345",
            "description": "상세 설명",
            "addImg1": "https://example.com/add1.jpg",
        }
        assert fetcher.needs_detail_fetch(product_full) is False

        # 설명이 없는 경우
        product_no_desc = {"productNo": "12346", "addImg1": "https://example.com/add1.jpg"}
        assert fetcher.needs_detail_fetch(product_no_desc) is True

        # 추가 이미지가 없는 경우
        product_no_img = {"productNo": "12347", "description": "설명"}
        assert fetcher.needs_detail_fetch(product_no_img) is True

    def test_run_incremental(self, fetcher):
        """증분 동기화 테스트"""
        # Mock 응답 설정
        mock_product = {
            "productNo": "12345",
            "productNm": "테스트 상품",
            "supplyPrice": 10000,
            "salePrice": 15000,
            "stockQty": 100,
            "productStatus": "Y",
            "category1": "001",
            "categoryNm1": "패션의류",
            "mainImg": "https://example.com/img.jpg",
            "description": "상품 설명",
            "addImg1": "https://example.com/add1.jpg",
        }

        mock_result = {
            "total_count": 1,
            "products": [mock_product],
            "has_next": False,
        }
        fetcher.client.search_products.return_value = mock_result

        # 상세 조회도 같은 데이터 반환
        fetcher.client.get_product_detail.return_value = mock_product

        # 증분 동기화 실행
        fetcher.run_incremental(max_pages=1, category="001")

        # 통계 확인
        stats = fetcher.stats
        assert stats["fetched"] == 1
        assert stats["saved"] == 1
        assert stats["duplicates"] == 0
        assert stats["errors"] == 0

        # 저장된 데이터 확인
        saved_products = fetcher.storage.list_raw_products(supplier_id="domeme")
        assert len(saved_products) == 1
        assert saved_products[0]["supplier_product_id"] == "12345"

    def test_duplicate_handling(self, fetcher):
        """중복 처리 테스트"""
        # 동일한 상품 데이터
        product = {
            "productNo": "12345",
            "productNm": "테스트 상품",
            "supplyPrice": 10000,
        }

        # 첫 번째 저장
        record_id1 = fetcher.save_raw(product)
        assert record_id1 is not None

        # 두 번째 저장 (중복)
        record_id2 = fetcher.save_raw(product)
        assert record_id2 is None

        # 통계 확인
        stats = fetcher.stats
        assert stats["saved"] == 1
        assert stats["duplicates"] == 1

    def test_error_handling(self, fetcher):
        """오류 처리 테스트"""
        # API 오류 설정
        fetcher.client.search_products.side_effect = DomemeAPIError("API 오류")

        # 증분 동기화 실행
        fetcher.run_incremental(max_pages=1, category="001")

        # 통계 확인
        stats = fetcher.stats
        assert stats["errors"] > 0
        assert stats["saved"] == 0


class TestDomemeTransformer:
    """도매매 변환기 테스트"""

    def test_transform_to_standard(self):
        """표준 형식 변환 테스트"""
        from dropshipping.models.product import ProductStatus
        from dropshipping.transformers.domeme import DomemeTransformer

        transformer = DomemeTransformer()

        # 도매매 원본 데이터
        raw_data = {
            "productNo": "12345",
            "productNm": "테스트 상품",
            "supplyPrice": 10000,
            "salePrice": 15000,
            "consumerPrice": 20000,
            "stockQty": 100,
            "productStatus": "Y",
            "category1": "001",
            "categoryNm1": "패션의류",
            "brandNm": "TestBrand",
            "makerNm": "TestMaker",
            "origin": "Korea",
            "mainImg": "https://example.com/main.jpg",
            "addImg1": "https://example.com/add1.jpg",
            "description": "상품 설명",
            "deliveryPrice": 2500,
            "option1Nm": "색상",
            "option1Value": "블랙,화이트,그레이",
            "option2Nm": "사이즈",
            "option2Value": "S,M,L,XL",
        }

        # 변환 실행
        product = transformer.to_standard(raw_data)

        # 결과 검증
        assert product.id == "domeme_12345"
        assert product.supplier_id == "domeme"
        assert product.supplier_product_id == "12345"
        assert product.name == "테스트 상품"
        assert product.cost == 10000
        assert product.price == 15000
        assert product.list_price == 20000
        assert product.stock == 100
        assert product.status == ProductStatus.ACTIVE
        assert product.category_code == "001"
        assert product.category_name == "패션의류"
        assert product.brand == "TestBrand"
        assert product.manufacturer == "TestMaker"
        assert product.origin == "Korea"
        assert product.shipping_fee == 2500
        assert product.is_free_shipping is False

        # 이미지 검증
        assert len(product.images) == 2
        assert str(product.images[0].url) == "https://example.com/main.jpg"
        assert product.images[0].is_main is True
        assert str(product.images[1].url) == "https://example.com/add1.jpg"
        assert product.images[1].is_main is False

        # 옵션 검증
        assert len(product.options) == 2
        assert product.options[0].name == "색상"
        assert product.options[0].values == ["블랙", "화이트", "그레이"]
        assert product.options[1].name == "사이즈"
        assert product.options[1].values == ["S", "M", "L", "XL"]
