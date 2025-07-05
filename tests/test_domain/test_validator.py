"""
상품 검증기 테스트
"""

from datetime import datetime

import pytest

from dropshipping.domain.validator import ProductValidator
from dropshipping.models.product import ProductImage, ProductStatus, StandardProduct


class TestProductValidator:
    """상품 검증기 테스트"""

    @pytest.fixture
    def validator(self):
        """테스트용 검증기"""
        return ProductValidator()

    @pytest.fixture
    def valid_product(self):
        """유효한 상품"""
        return StandardProduct(
            id="test123",
            supplier_id="domeme",
            supplier_product_id="DM123",
            name="테스트 상품 - 고품질 무선 이어폰",
            brand="TestBrand",
            manufacturer="TestMaker",
            origin="Korea",
            description="이것은 테스트 상품입니다. 고품질 무선 이어폰으로 뛰어난 음질을 제공합니다.",
            category_code="002001",
            category_name="전자제품/이어폰",
            cost=20000,
            price=35000,
            list_price=40000,
            stock=100,
            status=ProductStatus.ACTIVE,
            images=[
                ProductImage(
                    url="https://example.com/image1.jpg", width=800, height=800, is_main=True
                ),
                ProductImage(url="https://example.com/image2.jpg"),
                ProductImage(url="https://example.com/image3.jpg"),
            ],
            shipping_fee=2500,
            shipping_method="택배",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def test_valid_product(self, validator, valid_product):
        """유효한 상품 검증"""
        result = validator.validate_product(valid_product)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.score > 0.8

    def test_missing_required_fields(self, validator):
        """필수 필드 누락"""
        product = StandardProduct(
            id="",  # 빈 ID
            supplier_id="domeme",
            supplier_product_id="DM123",
            name="",  # 빈 이름
            cost=1000,  # Valid cost to pass model validation
            price=10000,
            status=ProductStatus.ACTIVE,
        )

        result = validator.validate_product(product)

        assert not result.is_valid
        assert len(result.errors) >= 2  # id, name
        assert any(e["field"] == "id" for e in result.errors)
        assert any(e["field"] == "name" for e in result.errors)

    def test_banned_keywords(self, validator, valid_product):
        """금지 키워드 검증"""
        valid_product.name = "정품 레플리카 명품 가방"
        valid_product.description = "최고급 이미테이션 제품입니다"

        result = validator.validate_product(valid_product)

        assert not result.is_valid
        assert any("레플리카" in e["message"] for e in result.errors)
        assert any("이미테이션" in e["message"] for e in result.errors)

    def test_price_validation(self, validator, valid_product):
        """가격 검증"""
        # 판매가가 원가보다 낮은 경우
        valid_product.cost = 20000
        valid_product.price = 15000

        result = validator.validate_product(valid_product)

        assert result.is_valid  # 경고만 발생
        assert len(result.warnings) > 0
        assert any("원가보다 낮" in w["message"] for w in result.warnings)

    def test_marketplace_price_limits(self, validator, valid_product):
        """마켓플레이스별 가격 제한"""
        # 쿠팡 최소 가격 미만
        valid_product.price = 500

        result = validator.validate_product(valid_product, marketplace="coupang")

        assert not result.is_valid
        assert any("최소 가격" in e["message"] for e in result.errors)

    def test_text_length_validation(self, validator, valid_product):
        """텍스트 길이 검증"""
        # 짧은 상품명
        valid_product.name = "테스트"

        result = validator.validate_product(valid_product)

        assert len(result.warnings) > 0
        assert any("상품명이 너무 짧" in w["message"] for w in result.warnings)

        # 긴 상품명 (쿠팡 기준)
        valid_product.name = "A" * 150  # 150자

        result = validator.validate_product(valid_product, marketplace="coupang")

        assert not result.is_valid
        assert any("제한" in e["message"] and "초과" in e["message"] for e in result.errors)

    def test_image_validation(self, validator):
        """이미지 검증"""
        # 메인 이미지 없음
        product = StandardProduct(
            id="test",
            supplier_id="domeme",
            supplier_product_id="DM123",
            name="이미지 없는 상품",
            cost=10000,
            price=15000,
            status=ProductStatus.ACTIVE,
            images=[],
        )

        result = validator.validate_product(product)

        assert not result.is_valid
        assert any("이미지" in e["message"] for e in result.errors)

    def test_stock_status_validation(self, validator, valid_product):
        """재고/상태 검증"""
        # 재고 없는데 활성 상태
        valid_product.stock = 0
        valid_product.status = ProductStatus.ACTIVE

        result = validator.validate_product(valid_product)

        assert result.is_valid  # 경고만
        assert len(result.warnings) > 0
        assert any("재고가 없는데" in w["message"] for w in result.warnings)

        # 재고 있는데 품절 상태
        valid_product.stock = 100
        valid_product.status = ProductStatus.OUT_OF_STOCK

        result = validator.validate_product(valid_product)

        assert len(result.warnings) > 0
        assert any("재고가 있는데" in w["message"] for w in result.warnings)

    def test_quality_score_calculation(self, validator, valid_product):
        """품질 점수 계산"""
        # 완벽한 상품
        result = validator.validate_product(valid_product)
        assert result.score > 0.9

        # 경고가 있는 상품
        valid_product.description = "짧은 설명"
        result = validator.validate_product(valid_product)
        assert 0.5 < result.score < 1.0

        # 오류가 있는 상품
        valid_product.name = ""
        result = validator.validate_product(valid_product)
        assert result.score < 0.8

    def test_bulk_validation(self, validator, valid_product):
        """대량 검증"""
        products = []

        # 유효한 상품
        products.append(valid_product)

        # 문제 있는 상품
        invalid_product = StandardProduct(
            id="invalid",
            supplier_id="domeme",
            supplier_product_id="DM999",
            name="",  # 빈 이름
            cost=1000,
            price=2000,
            status=ProductStatus.ACTIVE,
            images=[],  # 이미지 없음
        )
        products.append(invalid_product)

        results = validator.validate_bulk(products)

        assert len(results) == 2
        assert results[valid_product.id].is_valid
        assert not results["invalid"].is_valid

    def test_validation_summary(self, validator, valid_product):
        """검증 요약"""
        products = [valid_product]

        # 문제 있는 상품 추가
        for i in range(3):
            p = StandardProduct(
                id=f"problem{i}",
                supplier_id="domeme",
                supplier_product_id=f"DM{i}",
                name=f"문제상품{i}",
                cost=1000,
                price=500 if i == 0 else 2000,  # 첫 번째는 역마진
                status=ProductStatus.ACTIVE,
            )
            products.append(p)

        results = validator.validate_bulk(products)
        summary = validator.get_validation_summary(results)

        assert summary["total_products"] == 4
        assert summary["valid_products"] >= 1
        assert summary["invalid_products"] >= 1
        assert 0 <= summary["validation_rate"] <= 1
