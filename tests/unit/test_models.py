"""
데이터 모델 단위 테스트
"""

import pytest
from decimal import Decimal
from datetime import datetime

from dropshipping.models.product import (
    StandardProduct,
    ProductImage,
    ProductOption,
    ProductVariant,
    ProductStatus,
    OptionType,
)
from dropshipping.tests.fixtures.mock_data import MockDataGenerator


class TestStandardProduct:
    """StandardProduct 모델 테스트"""

    def test_create_minimal_product(self):
        """최소 필수 정보로 상품 생성"""
        product = StandardProduct(
            id="test_001",
            supplier_id="test_supplier",
            supplier_product_id="SUP001",
            name="테스트 상품",
            cost=Decimal("10000"),
            price=Decimal("15000"),
        )

        assert product.id == "test_001"
        assert product.name == "테스트 상품"
        assert product.cost == Decimal("10000")
        assert product.price == Decimal("15000")
        assert product.status == ProductStatus.ACTIVE
        assert product.stock == 0

    def test_price_validation(self):
        """가격 유효성 검증"""
        # 음수 가격
        with pytest.raises(ValueError, match="가격은 0보다 커야"):
            StandardProduct(
                id="test",
                supplier_id="test",
                supplier_product_id="test",
                name="test",
                cost=Decimal("10000"),
                price=Decimal("-1000"),
            )

        # 음수 원가
        with pytest.raises(ValueError, match="원가는 0보다 커야"):
            StandardProduct(
                id="test",
                supplier_id="test",
                supplier_product_id="test",
                name="test",
                cost=Decimal("-1000"),
                price=Decimal("10000"),
            )

    def test_margin_calculation(self):
        """마진 계산 테스트"""
        product = StandardProduct(
            id="test",
            supplier_id="test",
            supplier_product_id="test",
            name="test",
            cost=Decimal("10000"),
            price=Decimal("15000"),
        )

        assert product.margin == Decimal("5000")
        assert product.margin_rate == Decimal("33.33333333333333333333333333")

    def test_main_image_property(self):
        """대표 이미지 속성 테스트"""
        images = [
            ProductImage(url="http://example.com/1.jpg", is_main=False, order=0),
            ProductImage(url="http://example.com/2.jpg", is_main=True, order=1),
            ProductImage(url="http://example.com/3.jpg", is_main=False, order=2),
        ]

        product = MockDataGenerator.generate_product()
        product.images = images

        assert str(product.main_image.url) == "http://example.com/2.jpg"

    def test_ensure_main_image_validator(self):
        """대표 이미지 자동 설정 테스트"""
        # StandardProduct 생성 시 images를 직접 전달
        product = StandardProduct(
            id="test",
            supplier_id="test",
            supplier_product_id="test",
            name="test",
            cost=Decimal("10000"),
            price=Decimal("15000"),
            images=[
                ProductImage(url="http://example.com/1.jpg", is_main=False),
                ProductImage(url="http://example.com/2.jpg", is_main=False),
            ],
        )

        # 첫 번째 이미지가 자동으로 대표 이미지로 설정되어야 함
        assert product.images[0].is_main is True

    def test_serialization(self):
        """직렬화 테스트"""
        product = MockDataGenerator.generate_product()

        # dict 변환
        product_dict = product.to_dict()
        assert isinstance(product_dict, dict)
        assert product_dict["id"] == product.id

        # JSON 변환
        product_json = product.to_json()
        assert isinstance(product_json, str)
        assert product.id in product_json


class TestProductImage:
    """ProductImage 모델 테스트"""

    def test_create_image(self):
        """이미지 생성 테스트"""
        image = ProductImage(
            url="https://example.com/image.jpg", alt="상품 이미지", is_main=True, order=0
        )

        assert str(image.url) == "https://example.com/image.jpg"
        assert image.alt == "상품 이미지"
        assert image.is_main is True
        assert image.order == 0

    def test_url_validation(self):
        """URL 유효성 검증"""
        with pytest.raises(ValueError):
            ProductImage(url="not-a-valid-url")


class TestProductOption:
    """ProductOption 모델 테스트"""

    def test_create_option(self):
        """옵션 생성 테스트"""
        option = ProductOption(
            name="색상", type=OptionType.SELECT, values=["빨강", "파랑", "노랑"], required=True
        )

        assert option.name == "색상"
        assert option.type == "select"
        assert len(option.values) == 3
        assert option.required is True

    def test_default_values(self):
        """기본값 테스트"""
        option = ProductOption(name="사이즈")

        assert option.type == "select"
        assert option.values == []
        assert option.required is True


class TestProductVariant:
    """ProductVariant 모델 테스트"""

    def test_create_variant(self):
        """변형 생성 테스트"""
        variant = ProductVariant(
            sku="SKU001",
            options={"색상": "빨강", "사이즈": "L"},
            price=Decimal("20000"),
            stock=10,
            status=ProductStatus.ACTIVE,
        )

        assert variant.sku == "SKU001"
        assert variant.options["색상"] == "빨강"
        assert variant.price == Decimal("20000")
        assert variant.stock == 10
        assert variant.status == "active"


class TestMockDataGenerator:
    """Mock 데이터 생성기 테스트"""

    def test_generate_single_product(self):
        """단일 상품 생성 테스트"""
        product = MockDataGenerator.generate_product(supplier_id="domeme", category="fashion")

        assert product.supplier_id == "domeme"
        assert "fashion" in product.category_code
        assert product.cost > 0
        assert product.price > product.cost
        assert len(product.images) > 0

    def test_generate_multiple_products(self):
        """여러 상품 생성 테스트"""
        products = MockDataGenerator.generate_products(count=5)

        assert len(products) == 5
        assert all(isinstance(p, StandardProduct) for p in products)
        assert len(set(p.id for p in products)) == 5  # 모든 ID가 고유해야 함

    def test_generate_domeme_response(self):
        """도매매 응답 XML 생성 테스트"""
        xml_response = MockDataGenerator.generate_domeme_response(count=3)

        assert '<?xml version="1.0"' in xml_response
        assert "<code>00</code>" in xml_response
        assert "<totalCount>3</totalCount>" in xml_response
        assert xml_response.count("<product>") == 3
