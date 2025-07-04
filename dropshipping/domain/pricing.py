"""
가격 계산 모듈
마진율, 고정비용, 배송비 등을 고려한 판매가 계산
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any, List, Optional
from enum import Enum

from loguru import logger


class PricingMethod(Enum):
    """가격 책정 방식"""

    MARGIN_RATE = "margin_rate"  # 마진율 기반
    FIXED_MARGIN = "fixed_margin"  # 고정 마진
    COMPETITIVE = "competitive"  # 경쟁가 기반
    COST_PLUS = "cost_plus"  # 원가 + 고정비


@dataclass
class PricingRule:
    """가격 책정 규칙"""

    name: str
    method: PricingMethod
    priority: int = 0  # 우선순위 (높을수록 먼저 적용)

    # 조건
    min_cost: Optional[Decimal] = None
    max_cost: Optional[Decimal] = None
    category_codes: Optional[List[str]] = None
    supplier_ids: Optional[List[str]] = None

    # 가격 책정 파라미터
    margin_rate: Optional[Decimal] = None  # 마진율 (0.0 ~ 1.0)
    fixed_margin: Optional[Decimal] = None  # 고정 마진액
    min_margin_amount: Optional[Decimal] = None  # 최소 마진액
    max_margin_amount: Optional[Decimal] = None  # 최대 마진액

    # 추가 비용
    platform_fee_rate: Decimal = Decimal("0.1")  # 플랫폼 수수료율
    payment_fee_rate: Decimal = Decimal("0.03")  # 결제 수수료율
    packaging_cost: Decimal = Decimal("1000")  # 포장비
    handling_cost: Decimal = Decimal("500")  # 처리비용

    # 가격 조정
    round_to: int = 100  # 반올림 단위
    price_ending: Optional[int] = None  # 가격 끝자리 (예: 900)

    def matches(self, product: Dict[str, Any]) -> bool:
        """규칙이 상품에 적용되는지 확인"""
        cost = Decimal(str(product.get("cost", 0)))

        # 원가 범위 체크
        if self.min_cost and cost < self.min_cost:
            return False
        if self.max_cost and cost > self.max_cost:
            return False

        # 카테고리 체크
        if self.category_codes:
            category = product.get("category_code", "")
            if not any(category.startswith(code) for code in self.category_codes):
                return False

        # 공급사 체크
        if self.supplier_ids:
            supplier = product.get("supplier_id", "")
            if supplier not in self.supplier_ids:
                return False

        return True


class PricingCalculator:
    """가격 계산기"""

    def __init__(self):
        self.rules: List[PricingRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self):
        """기본 가격 규칙 설정"""
        # 저가 상품 규칙 (원가 1만원 미만)
        self.add_rule(
            PricingRule(
                name="저가상품",
                method=PricingMethod.MARGIN_RATE,
                priority=10,
                max_cost=Decimal("10000"),
                margin_rate=Decimal("0.5"),  # 50% 마진
                min_margin_amount=Decimal("2000"),  # 최소 2000원
            )
        )

        # 중가 상품 규칙 (원가 1만원 ~ 5만원)
        self.add_rule(
            PricingRule(
                name="중가상품",
                method=PricingMethod.MARGIN_RATE,
                priority=9,
                min_cost=Decimal("10000"),
                max_cost=Decimal("50000"),
                margin_rate=Decimal("0.3"),  # 30% 마진
                min_margin_amount=Decimal("3000"),  # 최소 3000원
            )
        )

        # 고가 상품 규칙 (원가 5만원 이상)
        self.add_rule(
            PricingRule(
                name="고가상품",
                method=PricingMethod.MARGIN_RATE,
                priority=8,
                min_cost=Decimal("50000"),
                margin_rate=Decimal("0.2"),  # 20% 마진
                min_margin_amount=Decimal("10000"),  # 최소 10000원
            )
        )

        # 기본 규칙 (모든 상품)
        self.add_rule(
            PricingRule(
                name="기본규칙",
                method=PricingMethod.COST_PLUS,
                priority=0,
                margin_rate=Decimal("0.25"),  # 25% 마진
            )
        )

    def add_rule(self, rule: PricingRule):
        """가격 규칙 추가"""
        self.rules.append(rule)
        # 우선순위 순으로 정렬
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"가격 규칙 추가: {rule.name}")

    def calculate_price(self, product: Dict[str, Any]) -> Dict[str, Decimal]:
        """
        상품 가격 계산

        Args:
            product: 상품 정보 (cost, shipping_fee 등 포함)

        Returns:
            계산된 가격 정보
        """
        # 기본 정보 추출
        if "cost" not in product or product["cost"] is None:
            raise ValueError("원가(cost) 정보가 없습니다")

        try:
            cost = Decimal(str(product["cost"]))
            if cost <= 0:
                raise ValueError("원가는 0보다 커야 합니다")
        except (TypeError, ValueError, ArithmeticError) as e:
            raise ValueError(f"원가 형식이 올바르지 않습니다: {product.get('cost')}")

        shipping_fee = Decimal(str(product.get("shipping_fee", 0)))

        # 적용할 규칙 찾기
        rule = self._find_applicable_rule(product)
        if not rule:
            raise ValueError("적용 가능한 가격 규칙이 없습니다")

        logger.debug(f"가격 규칙 적용: {rule.name}")

        # 기본 판매가 계산
        base_price = self._calculate_base_price(cost, rule)

        # 추가 비용 계산
        additional_costs = self._calculate_additional_costs(base_price, rule)

        # 최종 가격 계산
        final_price = base_price + additional_costs["total_additional"]

        # 마진 검증 및 조정
        final_price = self._validate_margin(cost, final_price, rule)

        # 가격 반올림
        final_price = self._round_price(final_price, rule)

        # 추가 비용 재계산 (반올림 후)
        additional_costs = self._calculate_additional_costs(final_price, rule)
        total_cost = cost + additional_costs["total_additional"]

        # 반올림 후 마진 재검증
        actual_margin = final_price - total_cost
        if rule.min_margin_amount and actual_margin < rule.min_margin_amount:
            # 최소 마진을 보장하도록 가격 재조정
            needed_price = total_cost + rule.min_margin_amount
            # 반올림을 고려하여 가격 설정
            if rule.round_to > 0:
                # 반올림 단위로 올림
                needed_price = ((needed_price + rule.round_to - 1) // rule.round_to) * rule.round_to
            final_price = needed_price
            # 추가 비용 최종 계산
            additional_costs = self._calculate_additional_costs(final_price, rule)
            total_cost = cost + additional_costs["total_additional"]

        # 배송비 포함 총액
        total_price = final_price + shipping_fee

        # 실제 마진 계산
        actual_margin = final_price - total_cost
        actual_margin_rate = (actual_margin / final_price) if final_price > 0 else Decimal("0")

        return {
            "cost": cost,
            "base_price": base_price,
            "additional_costs": additional_costs["total_additional"],
            "final_price": final_price,
            "shipping_fee": shipping_fee,
            "total_price": total_price,
            "margin_amount": actual_margin,
            "margin_rate": actual_margin_rate,
            "applied_rule": rule.name,
            "breakdown": {
                "platform_fee": additional_costs["platform_fee"],
                "payment_fee": additional_costs["payment_fee"],
                "packaging_cost": additional_costs["packaging_cost"],
                "handling_cost": additional_costs["handling_cost"],
            },
        }

    def _find_applicable_rule(self, product: Dict[str, Any]) -> Optional[PricingRule]:
        """적용 가능한 규칙 찾기"""
        for rule in self.rules:
            if rule.matches(product):
                return rule
        return None

    def _calculate_base_price(self, cost: Decimal, rule: PricingRule) -> Decimal:
        """기본 판매가 계산"""
        if rule.method == PricingMethod.MARGIN_RATE:
            # 마진율 기반
            if rule.margin_rate:
                base_price = cost / (1 - rule.margin_rate)
            else:
                base_price = cost * Decimal("1.3")  # 기본 30% 마진

        elif rule.method == PricingMethod.FIXED_MARGIN:
            # 고정 마진
            margin = rule.fixed_margin or Decimal("5000")
            base_price = cost + margin

        elif rule.method == PricingMethod.COST_PLUS:
            # 원가 + 고정비
            margin_rate = rule.margin_rate or Decimal("0.25")
            base_price = cost * (1 + margin_rate)

        else:
            # 기본값
            base_price = cost * Decimal("1.3")

        return base_price

    def _calculate_additional_costs(
        self, base_price: Decimal, rule: PricingRule
    ) -> Dict[str, Decimal]:
        """추가 비용 계산"""
        platform_fee = base_price * rule.platform_fee_rate
        payment_fee = base_price * rule.payment_fee_rate
        packaging_cost = rule.packaging_cost
        handling_cost = rule.handling_cost

        total = platform_fee + payment_fee + packaging_cost + handling_cost

        return {
            "platform_fee": platform_fee,
            "payment_fee": payment_fee,
            "packaging_cost": packaging_cost,
            "handling_cost": handling_cost,
            "total_additional": total,
        }

    def _validate_margin(self, cost: Decimal, price: Decimal, rule: PricingRule) -> Decimal:
        """마진 검증 및 조정"""
        # 추가 비용을 고려한 총 원가
        additional_costs = self._calculate_additional_costs(price, rule)
        total_cost = cost + additional_costs["total_additional"]

        # 실제 마진 = 판매가 - 총 원가
        margin = price - total_cost

        # 최소 마진 체크
        if rule.min_margin_amount and margin < rule.min_margin_amount:
            # 최소 마진을 보장하는 가격 계산
            price = total_cost + rule.min_margin_amount
            logger.debug(f"최소 마진 적용: {rule.min_margin_amount}")

        # 최대 마진 체크
        if rule.max_margin_amount:
            margin = price - total_cost
            if margin > rule.max_margin_amount:
                price = total_cost + rule.max_margin_amount
                logger.debug(f"최대 마진 적용: {rule.max_margin_amount}")

        return price

    def _round_price(self, price: Decimal, rule: PricingRule) -> Decimal:
        """가격 반올림"""
        # 반올림 단위
        round_to = rule.round_to
        if round_to > 0:
            price = (price // round_to) * round_to

        # 끝자리 조정
        if rule.price_ending is not None:
            base = (price // 1000) * 1000
            price = base + rule.price_ending

        return price

    def calculate_bulk_prices(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """여러 상품의 가격 일괄 계산"""
        results = []

        for product in products:
            try:
                pricing = self.calculate_price(product)
                result = product.copy()
                result.update(
                    {
                        "calculated_price": pricing["final_price"],
                        "total_price": pricing["total_price"],
                        "margin_amount": pricing["margin_amount"],
                        "margin_rate": float(pricing["margin_rate"]),
                        "pricing_details": pricing,
                    }
                )
                results.append(result)

            except Exception as e:
                logger.error(f"가격 계산 실패 ({product.get('id', 'unknown')}): {str(e)}")
                result = product.copy()
                result["pricing_error"] = str(e)
                results.append(result)

        return results
