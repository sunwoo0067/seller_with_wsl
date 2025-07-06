import pytest
from unittest.mock import Mock
from decimal import Decimal

from dropshipping.domain.pricing import PricingEngine
from dropshipping.storage.supabase_storage import SupabaseStorage


@pytest.fixture
def mock_supabase_storage():
    """SupabaseStorage를 Mocking하는 픽스처"""
    mock_storage = Mock(spec=SupabaseStorage)
    mock_storage.get_pricing_rules.return_value = sorted(
        [
            # 패션 카테고리 특별 규칙
            {
                "name": "패션 카테고리 규칙",
                "priority": 15,
                "conditions": {"category_codes": ["001", "002"]},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.4, "min_margin_amount": 5000},
                "additional_costs": {
                    "platform_fee_rate": 0.1,
                    "payment_fee_rate": 0.03,
                    "packaging_cost": 1200,
                    "handling_cost": 800,
                },
                "round_to": 900,
                "is_active": True,
            },
            # 저가 상품 규칙 (1만원 미만)
            {
                "name": "저가 상품 규칙",
                "priority": 10,
                "conditions": {"max_cost": 10000},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.5, "min_margin_amount": 2000},
                "additional_costs": {
                    "platform_fee_rate": 0.1,
                    "payment_fee_rate": 0.03,
                    "packaging_cost": 1000,
                    "handling_cost": 500,
                },
                "round_to": 100,
                "is_active": True,
            },
            # 중가 상품 규칙 (1만원 ~ 5만원)
            {
                "name": "중가 상품 규칙",
                "priority": 9,
                "conditions": {"min_cost": 10000, "max_cost": 50000},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.3, "min_margin_amount": 3000},
                "additional_costs": {
                    "platform_fee_rate": 0.1,
                    "payment_fee_rate": 0.03,
                    "packaging_cost": 1000,
                    "handling_cost": 500,
                },
                "round_to": 100,
                "is_active": True,
            },
            # 고가 상품 규칙 (5만원 이상)
            {
                "name": "고가 상품 규칙",
                "priority": 8,
                "conditions": {"min_cost": 50000},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.2, "min_margin_amount": 10000},
                "additional_costs": {
                    "platform_fee_rate": 0.1,
                    "payment_fee_rate": 0.03,
                    "packaging_cost": 1500,
                    "handling_cost": 1000,
                },
                "round_to": 1000,
                "is_active": True,
            },
            # 기본 규칙 (fallback) - seed_data.sql에서 변경된 값 반영
            {
                "name": "기본 규칙",
                "priority": 0,
                "conditions": {},
                "pricing_method": "margin_rate",
                "pricing_params": {"margin_rate": 0.35, "min_margin_amount": 3000},
                "additional_costs": {
                    "platform_fee_rate": 0.1,
                    "payment_fee_rate": 0.03,
                    "packaging_cost": 1000,
                    "handling_cost": 500,
                },
                "round_to": 100,
                "is_active": True,
            },
        ],
        key=lambda x: x["priority"],
        reverse=True,
    )
    return mock_storage


@pytest.fixture
def pricing_engine(mock_supabase_storage):
    """PricingEngine 인스턴스 픽스처"""
    return PricingEngine(mock_supabase_storage)


def test_apply_pricing_low_cost_product(pricing_engine):
    """저가 상품 규칙 적용 테스트"""
    cost = Decimal("5000")
    product_data = {"category_code": "003", "supplier_id": "domeme"}
    expected_price = Decimal("13200")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price


def test_apply_pricing_mid_cost_product(pricing_engine):
    """중가 상품 규칙 적용 테스트"""
    cost = Decimal("25000")
    product_data = {"category_code": "003", "supplier_id": "domeme"}
    expected_price = Decimal("42800")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price


def test_apply_pricing_high_cost_product(pricing_engine):
    """고가 상품 규칙 적용 테스트"""
    cost = Decimal("60000")
    product_data = {"category_code": "003", "supplier_id": "domeme"}
    expected_price = Decimal("89000")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price


def test_apply_pricing_fashion_category(pricing_engine):
    """패션 카테고리 특별 규칙 적용 테스트"""
    cost = Decimal("10000")
    product_data = {"category_code": "001", "supplier_id": "domeme"}
    expected_price = Decimal("21600")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price


def test_apply_pricing_fallback_rule(pricing_engine):
    """기본 규칙 (fallback) 적용 테스트"""
    cost = Decimal("100")
    product_data = {"category_code": "999", "supplier_id": "unknown"}  # 어떤 규칙에도 해당 안됨
    expected_price = Decimal("4100")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price


def test_reload_rules(pricing_engine, mock_supabase_storage):
    """규칙 재로드 테스트"""
    # 초기 로드 확인
    cost = Decimal("5000")
    product_data = {"category_code": "003", "supplier_id": "domeme"}
    assert pricing_engine.apply_pricing(cost, product_data) == Decimal("13200")

    # Mock 데이터 변경 (기본 규칙의 마진율 변경)
    mock_supabase_storage.get_pricing_rules.return_value = [
        {
            "name": "기본 규칙",
            "priority": 0,
            "conditions": {},
            "pricing_method": "margin_rate",
            "pricing_params": {"margin_rate": 0.5, "min_margin_amount": 1000},
            "additional_costs": {
                "platform_fee_rate": 0.1,
                "payment_fee_rate": 0.03,
                "packaging_cost": 1000,
                "handling_cost": 500,
            },
            "round_to": 100,
            "is_active": True,
        },
    ]

    # 규칙 재로드
    pricing_engine.reload_rules()

    # 변경된 규칙 확인
    expected_price_after_reload = Decimal("13200")
    assert pricing_engine.apply_pricing(cost, product_data) == expected_price_after_reload


def test_no_matching_rule(pricing_engine, mock_supabase_storage):
    """일치하는 규칙이 없을 때 에러 발생 테스트"""
    mock_supabase_storage.get_pricing_rules.return_value = []  # 모든 규칙 제거
    pricing_engine.reload_rules()

    cost = Decimal("10000")
    product_data = {"category_code": "003", "supplier_id": "domeme"}

    with pytest.raises(ValueError, match="No matching pricing rule found."):
        pricing_engine.apply_pricing(cost, product_data)
