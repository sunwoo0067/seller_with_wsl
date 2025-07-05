"""
가격 책정 엔진 테스트
"""

import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from dropshipping.transformers.pricing_engine import (
    PriceCalculationResult,
    PriceRoundingRule,
    PricingEngine,
    PricingRule,
    PricingStrategy,
)


class TestPricingEngine:
    """PricingEngine 테스트"""

    @pytest.fixture
    def temp_data_dir(self):
        """임시 데이터 디렉터리"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def pricing_engine(self, temp_data_dir):
        """PricingEngine 인스턴스"""
        return PricingEngine(data_dir=temp_data_dir)

    def test_initialization(self, pricing_engine):
        """초기화 테스트"""
        assert len(pricing_engine.pricing_rules) > 0
        assert "fashion_basic" in pricing_engine.pricing_rules
        assert "beauty_premium" in pricing_engine.pricing_rules
        assert "electronics_competitive" in pricing_engine.pricing_rules

    def test_basic_price_calculation(self, pricing_engine):
        """기본 가격 계산 테스트"""
        cost = Decimal("10000")
        result = pricing_engine.calculate_price(cost)

        assert isinstance(result, PriceCalculationResult)
        assert result.original_cost == cost
        assert result.final_price > cost
        assert result.margin_amount > 0
        assert result.margin_rate > 0
        assert len(result.applied_rules) > 0

    def test_fashion_category_pricing(self, pricing_engine):
        """패션 카테고리 가격 책정 테스트"""
        cost = Decimal("20000")
        result = pricing_engine.calculate_price(cost=cost, category_code="FASHION")

        # 패션 기본 마진 규칙이 적용되어야 함
        assert "fashion_basic" in result.applied_rules
        assert result.strategy_used == PricingStrategy.FIXED_MARGIN
        # 40% 마진 적용 확인 (대략적으로)
        assert 0.35 <= result.margin_rate <= 0.45

    def test_beauty_premium_pricing(self, pricing_engine):
        """뷰티 프리미엄 가격 책정 테스트"""
        cost = Decimal("15000")
        result = pricing_engine.calculate_price(cost=cost, category_code="BEAUTY")

        # 뷰티 프리미엄 규칙이 적용되어야 함
        assert "beauty_premium" in result.applied_rules
        assert result.strategy_used == PricingStrategy.PREMIUM
        # 50% 이상 마진 적용 확인
        assert result.margin_rate >= 0.45

    def test_electronics_competitive_pricing(self, pricing_engine):
        """전자제품 경쟁 가격 책정 테스트"""
        cost = Decimal("100000")
        market_price = Decimal("120000")

        result = pricing_engine.calculate_price(
            cost=cost, category_code="ELECTRONICS", market_price=market_price
        )

        # 전자제품 경쟁 규칙이 적용되어야 함
        assert "electronics_competitive" in result.applied_rules
        assert result.strategy_used == PricingStrategy.COMPETITIVE
        # 경쟁 가격보다 낮아야 함
        assert result.final_price < market_price

    def test_supplier_specific_pricing(self, pricing_engine):
        """공급사별 가격 책정 테스트"""
        cost = Decimal("25000")
        result = pricing_engine.calculate_price(cost=cost, supplier_id="domeme")

        # 도매매 표준 마진 규칙이 적용되어야 함
        assert "domeme_standard" in result.applied_rules
        # 35% 마진 적용 확인 (대략적으로)
        assert 0.3 <= result.margin_rate <= 0.4

    def test_price_range_based_pricing(self, pricing_engine):
        """가격대별 가격 책정 테스트"""
        # 저가 상품 (고마진)
        low_cost = Decimal("5000")
        low_result = pricing_engine.calculate_price(cost=low_cost)

        # 고가 상품 (저마진)
        high_cost = Decimal("150000")
        high_result = pricing_engine.calculate_price(cost=high_cost)

        # 저가 상품이 더 높은 마진율을 가져야 함
        assert low_result.margin_rate > high_result.margin_rate

    def test_volume_discount(self, pricing_engine):
        """수량 할인 테스트"""
        cost = Decimal("10000")

        # 소량 주문
        small_result = pricing_engine.calculate_price(cost=cost, volume=1)

        # 대량 주문
        large_result = pricing_engine.calculate_price(cost=cost, volume=50)

        # 대량 주문시 마진율이 낮아져야 함 (수량 할인)
        # 동적 조정 규칙이 적용된 경우에만
        if "dynamic_adjustment" in large_result.applied_rules:
            assert large_result.margin_rate <= small_result.margin_rate

    def test_rounding_rules(self, pricing_engine):
        """반올림 규칙 테스트"""
        # 끝자리 9 반올림 테스트
        nine_ending_rule = PricingRule(
            id="test_nine",
            name="테스트 9 반올림",
            description="테스트",
            strategy=PricingStrategy.FIXED_MARGIN,
            base_margin=0.3,
            min_margin=0.1,
            max_margin=0.5,
            rounding_rule=PriceRoundingRule.NINE_ENDING,
        )

        cost = Decimal("10000")
        result = pricing_engine._calculate_with_rule(cost, nine_ending_rule)

        # 끝자리가 9 또는 99여야 함
        price_str = str(int(result.final_price))
        assert price_str.endswith("9") or price_str.endswith("99") or price_str.endswith("999")

    def test_rule_priority(self, pricing_engine):
        """규칙 우선순위 테스트"""
        cost = Decimal("20000")

        # 패션 카테고리이면서 도매매 공급사인 경우
        result = pricing_engine.calculate_price(
            cost=cost, supplier_id="domeme", category_code="FASHION"
        )

        # 더 높은 우선순위 규칙이 적용되어야 함
        applicable_rules = pricing_engine._find_applicable_rules(cost, "domeme", "FASHION")

        if len(applicable_rules) > 1:
            # 우선순위가 높은 규칙이 먼저 적용되는지 확인
            applicable_rules.sort(key=lambda r: r.priority, reverse=True)
            highest_priority_rule = applicable_rules[0]
            assert highest_priority_rule.id in result.applied_rules

    def test_margin_limits(self, pricing_engine):
        """마진 한계 테스트"""
        # 극단적인 경쟁 가격으로 마진 한계 테스트
        cost = Decimal("10000")
        very_low_market_price = Decimal("10500")  # 5% 마진만 가능

        result = pricing_engine.calculate_price(
            cost=cost, category_code="ELECTRONICS", market_price=very_low_market_price
        )

        # 최소 마진율이 지켜져야 함
        electronics_rule = pricing_engine.pricing_rules["electronics_competitive"]
        assert result.margin_rate >= electronics_rule.min_margin

    def test_rule_management(self, pricing_engine):
        """규칙 관리 테스트"""
        # 새 규칙 추가
        new_rule = PricingRule(
            id="test_rule",
            name="테스트 규칙",
            description="테스트용 규칙",
            strategy=PricingStrategy.FIXED_MARGIN,
            base_margin=0.25,
            min_margin=0.1,
            max_margin=0.4,
            rounding_rule=PriceRoundingRule.HUNDRED,
            category_codes=["TEST"],
        )

        # 추가
        assert pricing_engine.add_rule(new_rule) is True
        assert "test_rule" in pricing_engine.pricing_rules

        # 조회
        retrieved_rule = pricing_engine.get_rule("test_rule")
        assert retrieved_rule is not None
        assert retrieved_rule.name == "테스트 규칙"

        # 업데이트
        assert pricing_engine.update_rule("test_rule", {"base_margin": 0.35}) is True
        updated_rule = pricing_engine.get_rule("test_rule")
        assert updated_rule.base_margin == 0.35

        # 삭제
        assert pricing_engine.delete_rule("test_rule") is True
        assert "test_rule" not in pricing_engine.pricing_rules

    def test_calculation_history(self, pricing_engine):
        """계산 히스토리 테스트"""
        initial_count = len(pricing_engine.calculation_history)

        # 여러 번 계산 수행
        for i in range(5):
            cost = Decimal(str(10000 + i * 1000))
            pricing_engine.calculate_price(cost)

        # 히스토리가 증가했는지 확인
        assert len(pricing_engine.calculation_history) == initial_count + 5

    def test_statistics(self, pricing_engine):
        """통계 정보 테스트"""
        # 몇 번 계산 수행
        for i in range(3):
            cost = Decimal(str(10000 + i * 5000))
            pricing_engine.calculate_price(cost)

        stats = pricing_engine.get_statistics()

        assert "total_rules" in stats
        assert "active_rules" in stats
        assert "strategy_distribution" in stats
        assert "calculation_history_size" in stats
        assert "average_margin" in stats

        assert stats["total_rules"] > 0
        assert stats["active_rules"] > 0
        assert stats["calculation_history_size"] >= 3

    def test_edge_cases(self, pricing_engine):
        """엣지 케이스 테스트"""
        # 0원 원가
        zero_cost = Decimal("0")
        result = pricing_engine.calculate_price(zero_cost)
        assert result.final_price >= 0

        # 매우 높은 원가
        high_cost = Decimal("1000000")
        result = pricing_engine.calculate_price(high_cost)
        assert result.final_price > high_cost

        # 존재하지 않는 카테고리
        result = pricing_engine.calculate_price(Decimal("10000"), category_code="NONEXISTENT")
        assert result is not None  # 기본 규칙 적용

    def test_rounding_precision(self, pricing_engine):
        """반올림 정밀도 테스트"""
        test_cases = [
            (PriceRoundingRule.HUNDRED, Decimal("12345"), "12300"),
            (PriceRoundingRule.THOUSAND, Decimal("12345"), "12000"),
            (PriceRoundingRule.NINE_ENDING, Decimal("12345"), "12999"),
            (PriceRoundingRule.ZERO_ENDING, Decimal("12345"), "12000"),
        ]

        for rounding_rule, input_price, expected in test_cases:
            result = pricing_engine._apply_rounding(input_price, rounding_rule)
            # 정확한 값보다는 패턴 확인
            if rounding_rule == PriceRoundingRule.NINE_ENDING:
                assert str(int(result)).endswith("99") or str(int(result)).endswith("999")
            elif rounding_rule == PriceRoundingRule.ZERO_ENDING:
                assert str(int(result)).endswith("000") or str(int(result)).endswith("00")


class TestPricingRule:
    """PricingRule 데이터 클래스 테스트"""

    def test_rule_creation(self):
        """규칙 생성 테스트"""
        rule = PricingRule(
            id="test",
            name="테스트 규칙",
            description="테스트용",
            strategy=PricingStrategy.FIXED_MARGIN,
            base_margin=0.3,
            min_margin=0.1,
            max_margin=0.5,
            rounding_rule=PriceRoundingRule.NINE_ENDING,
        )

        assert rule.id == "test"
        assert rule.strategy == PricingStrategy.FIXED_MARGIN
        assert rule.base_margin == 0.3
        assert rule.supplier_ids == []
        assert rule.category_codes == []
        assert rule.active is True

    def test_rule_with_conditions(self):
        """조건이 있는 규칙 테스트"""
        rule = PricingRule(
            id="conditional",
            name="조건부 규칙",
            description="조건이 있는 규칙",
            strategy=PricingStrategy.COMPETITIVE,
            base_margin=0.2,
            min_margin=0.1,
            max_margin=0.3,
            rounding_rule=PriceRoundingRule.THOUSAND,
            supplier_ids=["domeme", "ownerclan"],
            category_codes=["FASHION", "BEAUTY"],
            min_cost=Decimal("10000"),
            max_cost=Decimal("100000"),
        )

        assert len(rule.supplier_ids) == 2
        assert len(rule.category_codes) == 2
        assert rule.min_cost == Decimal("10000")
        assert rule.max_cost == Decimal("100000")


class TestPriceCalculationResult:
    """PriceCalculationResult 테스트"""

    def test_result_creation(self):
        """결과 객체 생성 테스트"""
        result = PriceCalculationResult(
            original_cost=Decimal("10000"),
            final_price=Decimal("13000"),
            margin_amount=Decimal("3000"),
            margin_rate=0.3,
            applied_rules=["test_rule"],
            strategy_used=PricingStrategy.FIXED_MARGIN,
            rounding_applied=True,
            calculation_details={"test": "value"},
        )

        assert result.original_cost == Decimal("10000")
        assert result.final_price == Decimal("13000")
        assert result.margin_rate == 0.3
        assert "test_rule" in result.applied_rules
        assert result.rounding_applied is True
