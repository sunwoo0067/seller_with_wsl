"""
가격 계산기 테스트
"""

import pytest
from decimal import Decimal

from dropshipping.domain.pricing import PricingCalculator, PricingRule, PricingMethod


class TestPricingCalculator:
    """가격 계산기 테스트"""

    @pytest.fixture
    def calculator(self):
        """테스트용 계산기"""
        return PricingCalculator()

    def test_calculate_low_price_product(self, calculator):
        """저가 상품 가격 계산"""
        product = {"id": "test1", "cost": 5000, "shipping_fee": 2500}

        result = calculator.calculate_price(product)

        # 기본 규칙: 50% 마진, 최소 2000원
        assert result["cost"] == Decimal("5000")
        assert result["margin_amount"] >= Decimal("2000")
        assert result["applied_rule"] == "저가상품"
        assert result["final_price"] > result["cost"]

    def test_calculate_mid_price_product(self, calculator):
        """중가 상품 가격 계산"""
        product = {"id": "test2", "cost": 25000, "shipping_fee": 0}

        result = calculator.calculate_price(product)

        # 중가 규칙: 30% 마진, 최소 3000원
        assert result["cost"] == Decimal("25000")
        assert result["margin_amount"] >= Decimal("3000")
        assert result["applied_rule"] == "중가상품"

        # 마진율 검증
        margin_rate = result["margin_rate"]
        assert 0.15 < float(margin_rate) < 0.35  # 추가비용 고려한 실제 마진

    def test_calculate_high_price_product(self, calculator):
        """고가 상품 가격 계산"""
        product = {"id": "test3", "cost": 80000, "shipping_fee": 0}

        result = calculator.calculate_price(product)

        # 고가 규칙: 20% 마진, 최소 10000원
        assert result["cost"] == Decimal("80000")
        assert result["margin_amount"] >= Decimal("10000")
        assert result["applied_rule"] == "고가상품"

    def test_additional_costs(self, calculator):
        """추가 비용 계산"""
        product = {"id": "test4", "cost": 10000, "shipping_fee": 0}

        result = calculator.calculate_price(product)
        breakdown = result["breakdown"]

        # 추가 비용 확인
        assert "platform_fee" in breakdown
        assert "payment_fee" in breakdown
        assert "packaging_cost" in breakdown
        assert "handling_cost" in breakdown

        # 추가 비용 합계
        total_additional = sum(breakdown.values())
        assert total_additional == result["additional_costs"]

    def test_price_rounding(self, calculator):
        """가격 반올림"""
        # 커스텀 규칙 추가
        rule = PricingRule(
            name="반올림테스트",
            method=PricingMethod.MARGIN_RATE,
            priority=100,
            margin_rate=Decimal("0.3"),
            round_to=1000,  # 1000원 단위
            price_ending=900,  # 900원으로 끝나도록
        )
        calculator.add_rule(rule)

        product = {"id": "test5", "cost": 12345, "shipping_fee": 0}

        result = calculator.calculate_price(product)

        # 가격이 XXX900 형태로 끝나는지 확인
        price_str = str(result["final_price"])
        assert price_str.endswith("900"), f"Price should end with 900, got {price_str}"

    def test_minimum_margin(self, calculator):
        """최소 마진 보장"""
        product = {"id": "test6", "cost": 1000, "shipping_fee": 0}

        result = calculator.calculate_price(product)

        # 저가 상품은 최소 2000원 마진
        assert result["margin_amount"] >= Decimal("2000")

    def test_custom_rule_priority(self, calculator):
        """커스텀 규칙 우선순위"""
        # 높은 우선순위 규칙 추가
        custom_rule = PricingRule(
            name="특별규칙",
            method=PricingMethod.FIXED_MARGIN,
            priority=20,  # 기본 규칙보다 높음
            fixed_margin=Decimal("5000"),
            min_cost=Decimal("1"),
            max_cost=Decimal("100000"),
        )
        calculator.add_rule(custom_rule)

        product = {"id": "test7", "cost": 5000, "shipping_fee": 0}

        result = calculator.calculate_price(product)

        # 커스텀 규칙이 적용되어야 함
        assert result["applied_rule"] == "특별규칙"

    def test_bulk_pricing(self, calculator):
        """대량 가격 계산"""
        products = [
            {"id": "p1", "cost": 5000, "shipping_fee": 2500},
            {"id": "p2", "cost": 25000, "shipping_fee": 0},
            {"id": "p3", "cost": 80000, "shipping_fee": 0},
        ]

        results = calculator.calculate_bulk_prices(products)

        assert len(results) == 3

        # 각 상품별로 적절한 규칙이 적용되었는지 확인
        assert results[0]["pricing_details"]["applied_rule"] == "저가상품"
        assert results[1]["pricing_details"]["applied_rule"] == "중가상품"
        assert results[2]["pricing_details"]["applied_rule"] == "고가상품"

    def test_error_handling(self, calculator):
        """오류 처리"""
        # 가격 정보가 없는 상품
        products = [
            {"id": "error1"},  # cost 없음
            {"id": "error2", "cost": "invalid"},  # 잘못된 형식
        ]

        results = calculator.calculate_bulk_prices(products)

        # 오류가 발생한 상품도 결과에 포함되어야 함
        assert len(results) == 2
        assert "pricing_error" in results[0]
        assert "pricing_error" in results[1]
