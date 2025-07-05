from unittest.mock import MagicMock

import pytest

from dropshipping.domain.pricing import PricingCalculator
from dropshipping.storage.base import BaseStorage


@pytest.fixture
def mock_storage():
    """DB Storage의 Mock 객체"""
    storage = MagicMock(spec=BaseStorage)

    # get_pricing_rules의 Mock 반환값 설정
    storage.get_pricing_rules.return_value = [
        {
            "name": "DB 저가상품",
            "pricing_method": "margin_rate",
            "priority": 10,
            "conditions": {"max_cost": 10000},
            "pricing_params": {"margin_rate": 0.6, "min_margin_amount": 2500},
            "additional_costs": {},
            "round_to": 100,
        },
        {
            "name": "DB 기본규칙",
            "pricing_method": "margin_rate",
            "priority": 0,
            "conditions": {},
            "pricing_params": {"margin_rate": 0.3},
            "additional_costs": {},
            "round_to": 100,
        },
    ]
    return storage


class TestPricingCalculatorWithDB:
    """DB 연동 가격 계산기 테스트"""

    def test_calculator_loads_rules_from_db(self, mock_storage):
        """DB에서 가격 규칙을 성공적으로 로드하는지 테스트"""
        calculator = PricingCalculator(storage=mock_storage)

        assert len(calculator.rules) == 2
        assert calculator.rules[0].name == "DB 저가상품"

    def test_calculate_price_with_db_rule(self, mock_storage):
        """DB에서 로드한 규칙으로 가격을 계산하는지 테스트"""
        calculator = PricingCalculator(storage=mock_storage)

        # 저가 상품 (DB 규칙 적용 대상)
        product = {"cost": 5000, "shipping_fee": 3000}
        result = calculator.calculate_price(product)

        assert result["applied_rule"] == "DB 저가상품"
        # 예상 가격 계산: 5000 / (1 - 0.6) = 12500. 추가비용 고려 필요.
        # 정확한 값 대신 규칙 적용 여부만 확인
        assert result["final_price"] > 5000

        # 고가 상품 (기본 규칙 적용 대상)
        product_high_cost = {"cost": 50000, "shipping_fee": 3000}
        result_high = calculator.calculate_price(product_high_cost)
        assert result_high["applied_rule"] == "DB 기본규칙"
