"""
데이터 변환기 단위 테스트
"""

import pytest
from decimal import Decimal

from dropshipping.transformers.domeme import DomemeTransformer
from dropshipping.models.product import StandardProduct, ProductStatus
from dropshipping.tests.fixtures.mock_data import MockDataGenerator


class TestDomemeTransformer:
    """도매매 변환기 테스트"""

    @pytest.fixture
    def transformer(self):
        """변환기 인스턴스"""
        return DomemeTransformer()

    @pytest.fixture
    def sample_xml(self):
        """샘플 XML 응답"""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <result>
            <code>00</code>
            <message>성공</message>
            <product>
                <productNo>TEST001</productNo>
                <productNm>테스트 티셔츠</productNm>
                <brandNm>테스트브랜드</brandNm>
                <makerNm>테스트제조사</makerNm>
                <origin>한국</origin>
                <supplyPrice>10000</supplyPrice>
                <salePrice>15000</salePrice>
                <consumerPrice>20000</consumerPrice>
                <stockQty>100</stockQty>
                <productStatus>Y</productStatus>
                <category1>의류</category1>
                <categoryNm1>상의</categoryNm1>
                <mainImg>http://example.com/main.jpg</mainImg>
                <addImg1>http://example.com/sub1.jpg</addImg1>
                <addImg2>http://example.com/sub2.jpg</addImg2>
                <deliveryPrice>3000</deliveryPrice>
                <deliveryType>택배</deliveryType>
                <description>편안한 착용감의 티셔츠입니다.</description>
                <option1Nm>색상</option1Nm>
                <option1Value>블랙, 화이트, 네이비</option1Value>
                <option2Nm>사이즈</option2Nm>
                <option2Value>S, M, L, XL</option2Value>
            </product>
        </result>"""

    def test_parse_xml_to_dict(self, transformer, sample_xml):
        """XML 파싱 테스트"""
        result = transformer.parse_xml_to_dict(sample_xml)

        assert result["code"] == "00"
        assert result["message"] == "성공"
        assert "product" in result
        assert result["product"]["productNo"] == "TEST001"

    def test_transform_to_standard(self, transformer):
        """표준 형식으로 변환 테스트"""
        raw_data = {
            "productNo": "TEST001",
            "productNm": "테스트 상품",
            "supplyPrice": "10000",
            "salePrice": "15000",
            "consumerPrice": "20000",
            "stockQty": "50",
            "productStatus": "Y",
            "category1": "CAT001",
            "categoryNm1": "카테고리1",
            "brandNm": "브랜드",
            "mainImg": "http://example.com/image.jpg",
            "description": "상품 설명",
        }

        product = transformer.to_standard(raw_data)

        assert isinstance(product, StandardProduct)
        assert product.id == "domeme_TEST001"
        assert product.supplier_id == "domeme"
        assert product.supplier_product_id == "TEST001"
        assert product.name == "테스트 상품"
        assert product.cost == Decimal("10000")
        assert product.price == Decimal("15000")
        assert product.list_price == Decimal("20000")
        assert product.stock == 50
        assert product.status == ProductStatus.ACTIVE

    def test_transform_with_options(self, transformer):
        """옵션 변환 테스트"""
        raw_data = MockDataGenerator.generate_raw_product_data("domeme")
        raw_data["option1Nm"] = "색상"
        raw_data["option1Value"] = "빨강, 파랑, 노랑"
        raw_data["option2Nm"] = "사이즈"
        raw_data["option2Value"] = "S, M, L"

        product = transformer.to_standard(raw_data)

        assert len(product.options) == 2
        assert product.options[0].name == "색상"
        assert product.options[0].values == ["빨강", "파랑", "노랑"]
        assert product.options[1].name == "사이즈"
        assert product.options[1].values == ["S", "M", "L"]

    def test_transform_with_images(self, transformer):
        """이미지 변환 테스트"""
        raw_data = MockDataGenerator.generate_raw_product_data("domeme")
        raw_data["mainImg"] = "http://example.com/main.jpg"
        raw_data["addImg1"] = "http://example.com/add1.jpg"
        raw_data["addImg2"] = "http://example.com/add2.jpg"

        product = transformer.to_standard(raw_data)

        assert len(product.images) == 3
        assert product.images[0].is_main is True
        assert str(product.images[0].url) == "http://example.com/main.jpg"
        assert product.images[1].is_main is False
        assert product.images[1].order == 1

    def test_status_conversion(self, transformer):
        """상태 변환 테스트"""
        # 활성 상태
        raw_data = MockDataGenerator.generate_raw_product_data("domeme")
        raw_data["productStatus"] = "Y"
        raw_data["stockQty"] = "100"
        product = transformer.to_standard(raw_data)
        assert product.status == ProductStatus.ACTIVE

        # 비활성 상태
        raw_data["productStatus"] = "N"
        product = transformer.to_standard(raw_data)
        assert product.status == ProductStatus.INACTIVE

        # 품절 상태
        raw_data["productStatus"] = "Y"
        raw_data["stockQty"] = "0"
        product = transformer.to_standard(raw_data)
        assert product.status == ProductStatus.SOLDOUT

    def test_batch_transform(self, transformer):
        """배치 변환 테스트"""
        raw_data_list = [MockDataGenerator.generate_raw_product_data("domeme") for _ in range(5)]

        products = transformer.batch_transform(raw_data_list)

        assert len(products) == 5
        assert all(isinstance(p, StandardProduct) for p in products)
        assert all(p.supplier_id == "domeme" for p in products)

    def test_transform_error_handling(self, transformer):
        """오류 처리 테스트"""
        # 필수 필드 누락
        invalid_data = {"productNm": "테스트"}  # productNo 누락

        product = transformer.transform(invalid_data)
        assert product is None
        assert len(transformer.errors) > 0

    def test_from_standard_not_implemented(self, transformer):
        """역변환 미구현 테스트"""
        product = MockDataGenerator.generate_product()

        with pytest.raises(NotImplementedError):
            transformer.from_standard(product)

    def test_safe_conversion_methods(self, transformer):
        """안전한 타입 변환 메서드 테스트"""
        assert transformer.safe_int("123") == 123
        assert transformer.safe_int("abc", 0) == 0
        assert transformer.safe_int(None, 10) == 10

        assert transformer.safe_float("123.45") == 123.45
        assert transformer.safe_float("abc", 0.0) == 0.0

        assert transformer.safe_str("test") == "test"
        assert transformer.safe_str(None, "default") == "default"
        assert transformer.safe_str("  test  ") == "test"  # trim

    def test_get_value_nested(self, transformer):
        """중첩 딕셔너리 값 추출 테스트"""
        data = {"product": {"price": {"value": 10000}}}

        assert transformer.get_value(data, "product.price.value") == 10000
        assert transformer.get_value(data, "product.price.currency", "KRW") == "KRW"
        assert transformer.get_value(data, "not.exist", "default") == "default"
