"""
가격 책정 규칙 엔진
카테고리별, 공급사별, 가격대별 마진율 적용 및 동적 가격 조정
"""

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

from loguru import logger


class PricingStrategy(Enum):
    """가격 책정 전략"""
    FIXED_MARGIN = "fixed_margin"      # 고정 마진율
    COMPETITIVE = "competitive"        # 경쟁 가격 기반
    DYNAMIC = "dynamic"               # 동적 가격 조정
    PREMIUM = "premium"               # 프리미엄 가격
    DISCOUNT = "discount"             # 할인 가격


class PriceRoundingRule(Enum):
    """가격 반올림 규칙"""
    NONE = "none"                     # 반올림 없음
    HUNDRED = "hundred"               # 100원 단위
    THOUSAND = "thousand"             # 1000원 단위
    NINE_ENDING = "nine_ending"       # 끝자리 9 (예: 9900, 19900)
    ZERO_ENDING = "zero_ending"       # 끝자리 0 (예: 10000, 20000)


@dataclass
class PricingRule:
    """가격 책정 규칙"""
    id: str
    name: str
    description: str
    strategy: PricingStrategy
    base_margin: float                # 기본 마진율 (0.0 ~ 1.0)
    min_margin: float                 # 최소 마진율
    max_margin: float                 # 최대 마진율
    rounding_rule: PriceRoundingRule
    
    # 적용 조건
    supplier_ids: List[str] = None
    category_codes: List[str] = None
    min_cost: Optional[Decimal] = None
    max_cost: Optional[Decimal] = None
    
    # 동적 조정 설정
    volume_discount: bool = False     # 수량 할인 적용
    seasonal_adjustment: bool = False # 계절 조정 적용
    competition_factor: float = 1.0   # 경쟁 요소 (0.8 ~ 1.2)
    
    # 메타데이터
    priority: int = 0                 # 우선순위 (높을수록 우선)
    active: bool = True
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.supplier_ids is None:
            self.supplier_ids = []
        if self.category_codes is None:
            self.category_codes = []
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class PriceCalculationResult:
    """가격 계산 결과"""
    original_cost: Decimal
    final_price: Decimal
    margin_amount: Decimal
    margin_rate: float
    applied_rules: List[str]
    strategy_used: PricingStrategy
    rounding_applied: bool
    calculation_details: Dict[str, Any]


class PricingEngine:
    """가격 책정 엔진"""

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Args:
            data_dir: 가격 규칙 데이터 디렉터리
        """
        self.data_dir = data_dir or Path(__file__).parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 가격 규칙들
        self.pricing_rules: Dict[str, PricingRule] = {}
        
        # 시장 가격 정보 (경쟁사 가격 등)
        self.market_prices: Dict[str, Decimal] = {}
        
        # 계산 히스토리
        self.calculation_history: List[PriceCalculationResult] = []
        
        # 초기 데이터 로드
        self._load_pricing_rules()

    def _load_pricing_rules(self):
        """가격 규칙 로드"""
        rules_file = self.data_dir / "pricing_rules.json"
        
        if rules_file.exists():
            try:
                with open(rules_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        # datetime 문자열을 객체로 변환
                        if item.get('created_at'):
                            item['created_at'] = datetime.fromisoformat(item['created_at'])
                        if item.get('updated_at'):
                            item['updated_at'] = datetime.fromisoformat(item['updated_at'])
                        
                        # Enum 변환
                        item['strategy'] = PricingStrategy(item['strategy'])
                        item['rounding_rule'] = PriceRoundingRule(item['rounding_rule'])
                        
                        # Decimal 변환
                        if item.get('min_cost'):
                            item['min_cost'] = Decimal(str(item['min_cost']))
                        if item.get('max_cost'):
                            item['max_cost'] = Decimal(str(item['max_cost']))
                        
                        rule = PricingRule(**item)
                        self.pricing_rules[rule.id] = rule
                        
                logger.info(f"가격 규칙 {len(self.pricing_rules)}개 로드 완료")
                return
            except Exception as e:
                logger.error(f"가격 규칙 로드 실패: {e}")
        
        # 기본 규칙 생성
        self._create_default_rules()
        self._save_pricing_rules()

    def _create_default_rules(self):
        """기본 가격 규칙 생성"""
        default_rules = [
            # 카테고리별 규칙
            PricingRule(
                id="fashion_basic",
                name="패션 기본 마진",
                description="패션의류 기본 마진율 적용",
                strategy=PricingStrategy.FIXED_MARGIN,
                base_margin=0.4,  # 40% 마진
                min_margin=0.2,
                max_margin=0.6,
                rounding_rule=PriceRoundingRule.NINE_ENDING,
                category_codes=["FASHION", "FASHION_WOMEN", "FASHION_MEN"],
                priority=10
            ),
            PricingRule(
                id="beauty_premium",
                name="뷰티 프리미엄 마진",
                description="뷰티 상품 프리미엄 마진율 적용",
                strategy=PricingStrategy.PREMIUM,
                base_margin=0.5,  # 50% 마진
                min_margin=0.3,
                max_margin=0.7,
                rounding_rule=PriceRoundingRule.NINE_ENDING,
                category_codes=["BEAUTY"],
                priority=15
            ),
            PricingRule(
                id="electronics_competitive",
                name="전자제품 경쟁 가격",
                description="전자제품 경쟁력 있는 가격 책정",
                strategy=PricingStrategy.COMPETITIVE,
                base_margin=0.15,  # 15% 마진
                min_margin=0.05,
                max_margin=0.25,
                rounding_rule=PriceRoundingRule.THOUSAND,
                category_codes=["ELECTRONICS"],
                competition_factor=0.95,  # 5% 할인
                priority=20
            ),
            # 가격대별 규칙
            PricingRule(
                id="low_price_high_margin",
                name="저가 상품 고마진",
                description="저가 상품에 높은 마진율 적용",
                strategy=PricingStrategy.FIXED_MARGIN,
                base_margin=0.6,  # 60% 마진
                min_margin=0.4,
                max_margin=0.8,
                rounding_rule=PriceRoundingRule.NINE_ENDING,
                min_cost=Decimal("1000"),
                max_cost=Decimal("10000"),
                priority=5
            ),
            PricingRule(
                id="high_price_low_margin",
                name="고가 상품 저마진",
                description="고가 상품에 낮은 마진율 적용",
                strategy=PricingStrategy.FIXED_MARGIN,
                base_margin=0.2,  # 20% 마진
                min_margin=0.1,
                max_margin=0.3,
                rounding_rule=PriceRoundingRule.THOUSAND,
                min_cost=Decimal("100000"),
                priority=5
            ),
            # 공급사별 규칙
            PricingRule(
                id="domeme_standard",
                name="도매매 표준 마진",
                description="도매매 공급사 표준 마진율",
                strategy=PricingStrategy.FIXED_MARGIN,
                base_margin=0.35,  # 35% 마진
                min_margin=0.2,
                max_margin=0.5,
                rounding_rule=PriceRoundingRule.NINE_ENDING,
                supplier_ids=["domeme"],
                priority=8
            ),
            # 동적 가격 조정 규칙
            PricingRule(
                id="dynamic_adjustment",
                name="동적 가격 조정",
                description="시장 상황에 따른 동적 가격 조정",
                strategy=PricingStrategy.DYNAMIC,
                base_margin=0.3,
                min_margin=0.15,
                max_margin=0.45,
                rounding_rule=PriceRoundingRule.NINE_ENDING,
                volume_discount=True,
                seasonal_adjustment=True,
                competition_factor=1.0,
                priority=1  # 낮은 우선순위 (기본값)
            )
        ]

        for rule in default_rules:
            self.pricing_rules[rule.id] = rule

    def calculate_price(
        self,
        cost: Decimal,
        supplier_id: str = None,
        category_code: str = None,
        product_name: str = None,
        market_price: Decimal = None,
        volume: int = 1
    ) -> PriceCalculationResult:
        """
        상품 가격 계산

        Args:
            cost: 원가
            supplier_id: 공급사 ID
            category_code: 카테고리 코드
            product_name: 상품명
            market_price: 시장 가격 (경쟁사 가격)
            volume: 수량

        Returns:
            PriceCalculationResult: 가격 계산 결과
        """
        # 적용 가능한 규칙 찾기
        applicable_rules = self._find_applicable_rules(
            cost, supplier_id, category_code
        )

        if not applicable_rules:
            # 기본 규칙 적용
            return self._apply_default_pricing(cost)

        # 우선순위 순으로 정렬
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)
        
        # 가장 높은 우선순위 규칙 적용
        primary_rule = applicable_rules[0]
        
        # 가격 계산
        result = self._calculate_with_rule(
            cost, primary_rule, market_price, volume
        )
        
        # 다른 규칙들의 영향도 고려
        for rule in applicable_rules[1:]:
            if rule.strategy == PricingStrategy.DYNAMIC:
                result = self._apply_dynamic_adjustment(result, rule)
        
        # 계산 히스토리 저장
        self.calculation_history.append(result)
        
        return result

    def _find_applicable_rules(
        self,
        cost: Decimal,
        supplier_id: str = None,
        category_code: str = None
    ) -> List[PricingRule]:
        """적용 가능한 규칙 찾기"""
        applicable = []

        for rule in self.pricing_rules.values():
            if not rule.active:
                continue

            # 공급사 조건 확인
            if rule.supplier_ids and supplier_id not in rule.supplier_ids:
                continue

            # 카테고리 조건 확인
            if rule.category_codes and category_code not in rule.category_codes:
                continue

            # 가격대 조건 확인
            if rule.min_cost and cost < rule.min_cost:
                continue
            if rule.max_cost and cost > rule.max_cost:
                continue

            applicable.append(rule)

        return applicable

    def _calculate_with_rule(
        self,
        cost: Decimal,
        rule: PricingRule,
        market_price: Decimal = None,
        volume: int = 1
    ) -> PriceCalculationResult:
        """특정 규칙으로 가격 계산"""
        calculation_details = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "strategy": rule.strategy.value,
            "base_margin": rule.base_margin,
            "volume": volume
        }

        # 기본 마진 적용
        margin_rate = rule.base_margin

        # 전략별 조정
        if rule.strategy == PricingStrategy.COMPETITIVE and market_price:
            # 경쟁 가격 기반 조정
            target_price = market_price * Decimal(str(rule.competition_factor))
            margin_amount = target_price - cost
            margin_rate = float(margin_amount / cost) if cost > 0 else 0
            calculation_details["market_price"] = str(market_price)
            calculation_details["competition_factor"] = rule.competition_factor

        elif rule.strategy == PricingStrategy.PREMIUM:
            # 프리미엄 전략: 기본 마진에 20% 추가
            margin_rate = min(margin_rate * 1.2, rule.max_margin)
            calculation_details["premium_factor"] = 1.2

        elif rule.strategy == PricingStrategy.DISCOUNT:
            # 할인 전략: 기본 마진에서 20% 감소
            margin_rate = max(margin_rate * 0.8, rule.min_margin)
            calculation_details["discount_factor"] = 0.8

        # 수량 할인 적용
        if rule.volume_discount and volume > 10:
            volume_discount_rate = min(0.1, (volume - 10) * 0.01)  # 최대 10% 할인
            margin_rate = max(margin_rate - volume_discount_rate, rule.min_margin)
            calculation_details["volume_discount_rate"] = volume_discount_rate

        # 마진율 범위 제한
        margin_rate = max(rule.min_margin, min(margin_rate, rule.max_margin))

        # 가격 계산
        margin_amount = cost * Decimal(str(margin_rate))
        raw_price = cost + margin_amount

        # 반올림 적용
        final_price = self._apply_rounding(raw_price, rule.rounding_rule)
        
        # 실제 마진 재계산
        actual_margin = final_price - cost
        actual_margin_rate = float(actual_margin / cost) if cost > 0 else 0

        calculation_details["raw_price"] = str(raw_price)
        calculation_details["rounding_rule"] = rule.rounding_rule.value
        calculation_details["final_margin_rate"] = actual_margin_rate

        return PriceCalculationResult(
            original_cost=cost,
            final_price=final_price,
            margin_amount=actual_margin,
            margin_rate=actual_margin_rate,
            applied_rules=[rule.id],
            strategy_used=rule.strategy,
            rounding_applied=final_price != raw_price,
            calculation_details=calculation_details
        )

    def _apply_rounding(self, price: Decimal, rounding_rule: PriceRoundingRule) -> Decimal:
        """가격 반올림 적용"""
        if rounding_rule == PriceRoundingRule.NONE:
            return price

        elif rounding_rule == PriceRoundingRule.HUNDRED:
            # 100원 단위 반올림
            return (price / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * 100

        elif rounding_rule == PriceRoundingRule.THOUSAND:
            # 1000원 단위 반올림
            return (price / 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * 1000

        elif rounding_rule == PriceRoundingRule.NINE_ENDING:
            # 끝자리 9로 만들기 (예: 12345 -> 12999)
            price_int = int(price)
            if price_int < 1000:
                return Decimal(str(price_int // 100 * 100 + 99))
            else:
                return Decimal(str(price_int // 1000 * 1000 + 999))

        elif rounding_rule == PriceRoundingRule.ZERO_ENDING:
            # 끝자리 0으로 만들기 (예: 12345 -> 12000)
            price_int = int(price)
            if price_int < 1000:
                return Decimal(str(price_int // 100 * 100))
            else:
                return Decimal(str(price_int // 1000 * 1000))

        return price

    def _apply_default_pricing(self, cost: Decimal) -> PriceCalculationResult:
        """기본 가격 책정 적용"""
        default_margin = 0.3  # 30% 기본 마진
        margin_amount = cost * Decimal(str(default_margin))
        raw_price = cost + margin_amount
        final_price = self._apply_rounding(raw_price, PriceRoundingRule.NINE_ENDING)
        
        actual_margin = final_price - cost
        actual_margin_rate = float(actual_margin / cost) if cost > 0 else 0

        return PriceCalculationResult(
            original_cost=cost,
            final_price=final_price,
            margin_amount=actual_margin,
            margin_rate=actual_margin_rate,
            applied_rules=["default"],
            strategy_used=PricingStrategy.FIXED_MARGIN,
            rounding_applied=final_price != raw_price,
            calculation_details={
                "rule": "default",
                "base_margin": default_margin,
                "rounding_rule": "nine_ending"
            }
        )

    def _apply_dynamic_adjustment(
        self,
        result: PriceCalculationResult,
        dynamic_rule: PricingRule
    ) -> PriceCalculationResult:
        """동적 조정 적용"""
        adjustment_factor = 1.0

        # 계절 조정 (예시)
        if dynamic_rule.seasonal_adjustment:
            current_month = datetime.now().month
            if current_month in [6, 7, 8]:  # 여름
                adjustment_factor *= 0.95  # 5% 할인
            elif current_month in [11, 12, 1]:  # 겨울
                adjustment_factor *= 1.05  # 5% 인상

        # 경쟁 요소 적용
        adjustment_factor *= dynamic_rule.competition_factor

        # 조정된 가격 계산
        if adjustment_factor != 1.0:
            adjusted_price = result.final_price * Decimal(str(adjustment_factor))
            adjusted_price = self._apply_rounding(adjusted_price, dynamic_rule.rounding_rule)
            
            # 결과 업데이트
            result.final_price = adjusted_price
            result.margin_amount = adjusted_price - result.original_cost
            result.margin_rate = float(result.margin_amount / result.original_cost)
            result.applied_rules.append(dynamic_rule.id)
            result.calculation_details["dynamic_adjustment"] = adjustment_factor

        return result

    def add_rule(self, rule: PricingRule) -> bool:
        """새로운 가격 규칙 추가"""
        try:
            self.pricing_rules[rule.id] = rule
            self._save_pricing_rules()
            logger.info(f"가격 규칙 추가: {rule.id} - {rule.name}")
            return True
        except Exception as e:
            logger.error(f"가격 규칙 추가 실패: {e}")
            return False

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """가격 규칙 업데이트"""
        if rule_id not in self.pricing_rules:
            logger.warning(f"존재하지 않는 규칙: {rule_id}")
            return False

        try:
            rule = self.pricing_rules[rule_id]
            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            
            rule.updated_at = datetime.now()
            self._save_pricing_rules()
            logger.info(f"가격 규칙 업데이트: {rule_id}")
            return True
        except Exception as e:
            logger.error(f"가격 규칙 업데이트 실패: {e}")
            return False

    def delete_rule(self, rule_id: str) -> bool:
        """가격 규칙 삭제"""
        if rule_id not in self.pricing_rules:
            logger.warning(f"존재하지 않는 규칙: {rule_id}")
            return False

        try:
            del self.pricing_rules[rule_id]
            self._save_pricing_rules()
            logger.info(f"가격 규칙 삭제: {rule_id}")
            return True
        except Exception as e:
            logger.error(f"가격 규칙 삭제 실패: {e}")
            return False

    def get_rule(self, rule_id: str) -> Optional[PricingRule]:
        """가격 규칙 조회"""
        return self.pricing_rules.get(rule_id)

    def list_rules(self, active_only: bool = True) -> List[PricingRule]:
        """가격 규칙 목록 조회"""
        rules = list(self.pricing_rules.values())
        if active_only:
            rules = [r for r in rules if r.active]
        return sorted(rules, key=lambda r: r.priority, reverse=True)

    def _save_pricing_rules(self):
        """가격 규칙을 파일에 저장"""
        rules_file = self.data_dir / "pricing_rules.json"
        try:
            data = []
            for rule in self.pricing_rules.values():
                rule_dict = asdict(rule)
                # datetime을 문자열로 변환
                rule_dict['created_at'] = rule.created_at.isoformat()
                rule_dict['updated_at'] = rule.updated_at.isoformat()
                # Enum을 문자열로 변환
                rule_dict['strategy'] = rule.strategy.value
                rule_dict['rounding_rule'] = rule.rounding_rule.value
                # Decimal을 문자열로 변환
                if rule_dict.get('min_cost'):
                    rule_dict['min_cost'] = str(rule.min_cost)
                if rule_dict.get('max_cost'):
                    rule_dict['max_cost'] = str(rule.max_cost)
                
                data.append(rule_dict)
            
            with open(rules_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"가격 규칙 저장 완료: {rules_file}")
        except Exception as e:
            logger.error(f"가격 규칙 저장 실패: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """가격 엔진 통계 정보"""
        active_rules = [r for r in self.pricing_rules.values() if r.active]
        
        strategy_counts = {}
        for rule in active_rules:
            strategy = rule.strategy.value
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            "total_rules": len(self.pricing_rules),
            "active_rules": len(active_rules),
            "strategy_distribution": strategy_counts,
            "calculation_history_size": len(self.calculation_history),
            "average_margin": self._calculate_average_margin(),
        }

    def _calculate_average_margin(self) -> float:
        """평균 마진율 계산"""
        if not self.calculation_history:
            return 0.0
        
        total_margin = sum(result.margin_rate for result in self.calculation_history[-100:])
        return total_margin / min(len(self.calculation_history), 100) 