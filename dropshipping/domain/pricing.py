from typing import Dict, Any, List
from decimal import Decimal

from dropshipping.storage.supabase_storage import SupabaseStorage


class PricingEngine:
    """
    가격 책정 규칙을 적용하여 상품의 최종 가격을 계산하는 엔진.
    """

    def __init__(self, storage: SupabaseStorage):
        self.storage = storage
        self._rules = []
        self._load_rules()

    def _load_rules(self):
        """
        Supabase에서 모든 가격 책정 규칙을 로드하여 캐시합니다.
        우선순위(priority)가 높은 규칙부터 적용됩니다.
        """
        self._rules = self.storage.get_pricing_rules(active_only=True)
        print(f"Loaded pricing rules: {self._rules}")
        # 규칙은 이미 priority 내림차순으로 정렬되어 로드됨

    def apply_pricing(self, cost: Decimal, product_data: Dict[str, Any]) -> Decimal:
        """
        주어진 원가와 상품 데이터를 기반으로 최종 판매 가격을 계산합니다.
        가장 먼저 일치하는 규칙이 적용됩니다.
        """
        for rule in self._rules:
            if self._match_rule(rule, cost, product_data):
                print(f"Applying rule: {rule.get('name')}, round_to: {rule.get('round_to')}")
                return self._calculate_price_by_rule(cost, rule)

        # 일치하는 규칙이 없으면 기본 규칙 (priority=0)이 적용될 것임
        # 만약 기본 규칙도 없다면 에러 또는 기본값 반환
        raise ValueError("No matching pricing rule found.")

    def _match_rule(
        self, rule: Dict[str, Any], cost: Decimal, product_data: Dict[str, Any]
    ) -> bool:
        """
        규칙의 조건을 상품 데이터와 비교하여 일치 여부를 판단합니다.
        """
        conditions = rule.get("conditions", {})

        # 원가 조건
        min_cost = conditions.get("min_cost")
        max_cost = conditions.get("max_cost")
        if min_cost is not None and cost < Decimal(str(min_cost)):
            return False
        if max_cost is not None and cost > Decimal(str(max_cost)):
            return False

        # 카테고리 조건
        category_codes = conditions.get("category_codes")
        if category_codes and product_data.get("category_code") not in category_codes:
            return False

        # 공급사 조건
        supplier_ids = conditions.get("supplier_ids")
        if supplier_ids and product_data.get("supplier_id") not in supplier_ids:
            return False

        return True

    def _calculate_price_by_rule(self, cost: Decimal, rule: Dict[str, Any]) -> Decimal:
        """
        일치하는 규칙에 따라 최종 가격을 계산합니다.
        """
        pricing_method = rule.get("pricing_method")
        pricing_params = rule.get("pricing_params", {})
        additional_costs = rule.get("additional_costs", {})

        calculated_price = Decimal(str(cost))

        if pricing_method == "margin_rate":
            margin_rate = Decimal(str(pricing_params.get("margin_rate", 0)))
            min_margin_amount = Decimal(str(pricing_params.get("min_margin_amount", 0)))

            # 마진율 적용
            calculated_price = cost / (Decimal("1") - margin_rate)

            # 최소 마진 금액 보장
            if (calculated_price - cost) < min_margin_amount:
                calculated_price = cost + min_margin_amount

        # 추가 비용 적용
        packaging_cost = Decimal(str(additional_costs.get("packaging_cost", 0)))
        handling_cost = Decimal(str(additional_costs.get("handling_cost", 0)))
        calculated_price = calculated_price + packaging_cost + handling_cost

        # 플랫폼 수수료 및 결제 수수료 역산
        platform_fee_rate = Decimal(str(additional_costs.get("platform_fee_rate", 0)))
        payment_fee_rate = Decimal(str(additional_costs.get("payment_fee_rate", 0)))
        total_fee_rate = platform_fee_rate + payment_fee_rate

        if total_fee_rate >= 1:  # 무한 루프 방지
            raise ValueError("Total fee rate cannot be 100% or more.")
        calculated_price = calculated_price / (Decimal("1") - total_fee_rate)

        # 가격 조정
        round_to = rule.get("round_to")
        if round_to:
            calculated_price = self._round_price(calculated_price, Decimal(str(round_to)))

        price_ending = rule.get("price_ending")
        if price_ending is not None:
            calculated_price = self._adjust_price_ending(calculated_price, price_ending)

        return calculated_price.quantize(Decimal("1"))  # 소수점 이하 버림

    def _round_price(self, price: Decimal, round_to: Decimal) -> Decimal:
        """
        가격을 지정된 단위로 반올림합니다.
        예: 12345를 100단위로 반올림 -> 12300 또는 12400
        """
        return (price / round_to).quantize(Decimal("1")).to_integral_value() * round_to

    def _adjust_price_ending(self, price: Decimal, ending: int) -> Decimal:
        """
        가격의 끝자리를 지정된 숫자로 조정합니다.
        예: 12345를 9로 조정 -> 12349
        """
        price_str = str(int(price))
        if not price_str.endswith(str(ending)):
            # 현재 끝자리를 제거하고 새로운 끝자리를 붙임
            price_without_ending = (
                price_str[: -len(str(ending))] if len(str(ending)) > 0 else price_str
            )
            return Decimal(price_without_ending + str(ending))
        return price

    def reload_rules(self):
        """
        캐시된 규칙 정보를 다시 로드합니다 (규칙 변경 시 호출).
        """
        self._rules = []
        self._load_rules()
