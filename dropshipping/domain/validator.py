"""
상품 검증 모듈
상품 데이터의 유효성 검사 및 품질 관리
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from dropshipping.models.product import ProductStatus, StandardProduct


class ValidationLevel(Enum):
    """검증 수준"""

    ERROR = "error"  # 필수 항목 오류
    WARNING = "warning"  # 권장 사항 미충족
    INFO = "info"  # 정보성 알림


@dataclass
class ValidationResult:
    """검증 결과"""

    is_valid: bool
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    info: List[Dict[str, Any]]
    score: float  # 품질 점수 (0.0 ~ 1.0)

    def add_error(self, field: str, message: str, details: Optional[Dict] = None):
        """오류 추가"""
        self.errors.append(
            {
                "field": field,
                "message": message,
                "level": ValidationLevel.ERROR.value,
                "details": details or {},
            }
        )
        self.is_valid = False

    def add_warning(self, field: str, message: str, details: Optional[Dict] = None):
        """경고 추가"""
        self.warnings.append(
            {
                "field": field,
                "message": message,
                "level": ValidationLevel.WARNING.value,
                "details": details or {},
            }
        )

    def add_info(self, field: str, message: str, details: Optional[Dict] = None):
        """정보 추가"""
        self.info.append(
            {
                "field": field,
                "message": message,
                "level": ValidationLevel.INFO.value,
                "details": details or {},
            }
        )


class ProductValidator:
    """상품 검증기"""

    def __init__(self):
        # 금지 키워드
        self.banned_keywords = [
            "가품",
            "짝퉁",
            "이미테이션",
            "레플리카",
            "복제품",
            "병행수입",
            "면세",
            "중고",
            "리퍼",
            "전시상품",
            "의료기기",
            "의약품",
            "건강기능식품",  # 인허가 필요 상품
        ]

        # 마켓플레이스별 제한사항
        self.marketplace_restrictions = {
            "coupang": {
                "min_price": 1000,
                "max_price": 100000000,
                "max_title_length": 100,
                "max_description_length": 50000,
                "required_images": 1,
                "max_images": 10,
            },
            "11st": {
                "min_price": 100,
                "max_price": 99999999,
                "max_title_length": 100,
                "max_description_length": 40000,
                "required_images": 1,
                "max_images": 20,
            },
            "smartstore": {
                "min_price": 100,
                "max_price": 999999999,
                "max_title_length": 100,
                "max_description_length": 50000,
                "required_images": 1,
                "max_images": 40,
            },
        }

    def validate_product(
        self, product: StandardProduct, marketplace: Optional[str] = None
    ) -> ValidationResult:
        """
        상품 검증

        Args:
            product: 검증할 상품
            marketplace: 대상 마켓플레이스

        Returns:
            검증 결과
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[], info=[], score=1.0)

        # 기본 필수 항목 검증
        self._validate_required_fields(product, result)

        # 금지 키워드 검증
        self._validate_banned_keywords(product, result)

        # 가격 검증
        self._validate_pricing(product, result, marketplace)

        # 텍스트 필드 검증
        self._validate_text_fields(product, result, marketplace)

        # 이미지 검증
        self._validate_images(product, result, marketplace)

        # 재고 및 상태 검증
        self._validate_stock_status(product, result)

        # 카테고리 검증
        self._validate_category(product, result)

        # 품질 점수 계산
        result.score = self._calculate_quality_score(result)

        return result

    def _validate_required_fields(self, product: StandardProduct, result: ValidationResult):
        """필수 필드 검증"""
        # 필수 필드 목록
        required_fields = {
            "id": "상품 ID",
            "name": "상품명",
            "price": "판매가",
            "cost": "원가",
            "status": "상태",
            "supplier_id": "공급사 ID",
            "supplier_product_id": "공급사 상품 ID",
        }

        for field, field_name in required_fields.items():
            value = getattr(product, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error(field, f"{field_name}이(가) 없습니다")

    def _validate_banned_keywords(self, product: StandardProduct, result: ValidationResult):
        """금지 키워드 검증"""
        text_to_check = f"{product.name} {product.description or ''}"

        for keyword in self.banned_keywords:
            if keyword in text_to_check:
                result.add_error("content", f"금지 키워드 포함: {keyword}", {"keyword": keyword})

    def _validate_pricing(
        self, product: StandardProduct, result: ValidationResult, marketplace: Optional[str]
    ):
        """가격 검증"""
        # 기본 가격 검증
        if product.price <= 0:
            result.add_error("price", "판매가는 0보다 커야 합니다")

        if product.cost <= 0:
            result.add_error("cost", "원가는 0보다 커야 합니다")

        if product.price <= product.cost:
            result.add_warning(
                "price",
                "판매가가 원가보다 낮거나 같습니다",
                {"price": product.price, "cost": product.cost},
            )

        # 마진율 검증
        if product.price > 0:
            margin_rate = (product.price - product.cost) / product.price
            if margin_rate < 0.1:  # 10% 미만
                result.add_warning(
                    "margin",
                    f"마진율이 너무 낮습니다: {margin_rate:.1%}",
                    {"margin_rate": margin_rate},
                )
            elif margin_rate > 0.8:  # 80% 초과
                result.add_warning(
                    "margin",
                    f"마진율이 비정상적으로 높습니다: {margin_rate:.1%}",
                    {"margin_rate": margin_rate},
                )

        # 마켓플레이스별 가격 제한
        if marketplace and marketplace in self.marketplace_restrictions:
            restrictions = self.marketplace_restrictions[marketplace]

            if product.price < restrictions["min_price"]:
                result.add_error(
                    "price",
                    f"{marketplace} 최소 가격({restrictions['min_price']}원) 미만",
                    {"min_price": restrictions["min_price"]},
                )

            if product.price > restrictions["max_price"]:
                result.add_error(
                    "price",
                    f"{marketplace} 최대 가격({restrictions['max_price']}원) 초과",
                    {"max_price": restrictions["max_price"]},
                )

    def _validate_text_fields(
        self, product: StandardProduct, result: ValidationResult, marketplace: Optional[str]
    ):
        """텍스트 필드 검증"""
        # 상품명 검증
        if len(product.name) < 10:
            result.add_warning("name", "상품명이 너무 짧습니다 (10자 미만)")

        if marketplace and marketplace in self.marketplace_restrictions:
            max_length = self.marketplace_restrictions[marketplace]["max_title_length"]
            if len(product.name) > max_length:
                result.add_error(
                    "name",
                    f"상품명이 {marketplace} 제한({max_length}자)을 초과합니다",
                    {"length": len(product.name), "max_length": max_length},
                )

        # 특수문자 검증
        special_chars = re.findall(r"[^\w\s\-.,!?()/]", product.name)
        if special_chars:
            result.add_warning("name", f"상품명에 특수문자 포함: {', '.join(set(special_chars))}")

        # 설명 검증
        if not product.description or len(product.description) < 50:
            result.add_warning("description", "상품 설명이 너무 짧습니다 (50자 미만)")

        if marketplace and product.description:
            restrictions = self.marketplace_restrictions.get(marketplace, {})
            max_desc_length = restrictions.get("max_description_length", 50000)
            if len(product.description) > max_desc_length:
                result.add_error(
                    "description",
                    f"상품 설명이 {marketplace} 제한({max_desc_length}자)을 초과합니다",
                )

    def _validate_images(
        self, product: StandardProduct, result: ValidationResult, marketplace: Optional[str]
    ):
        """이미지 검증"""
        # 이미지 확인
        if not product.images:
            result.add_error("images", "이미지가 없습니다")
            return

        # 메인 이미지 확인
        main_images = [img for img in product.images if img.is_main]
        if not main_images:
            result.add_error("images", "메인 이미지가 없습니다")
        elif len(main_images) > 1:
            result.add_warning("images", "메인 이미지가 여러 개입니다")

        # 전체 이미지 수
        total_images = len(product.images)

        if marketplace and marketplace in self.marketplace_restrictions:
            restrictions = self.marketplace_restrictions[marketplace]

            if total_images < restrictions["required_images"]:
                result.add_error(
                    "images",
                    f"최소 이미지 수({restrictions['required_images']}개) 미충족",
                    {"total_images": total_images},
                )

            if total_images > restrictions["max_images"]:
                result.add_warning(
                    "images",
                    f"최대 이미지 수({restrictions['max_images']}개) 초과",
                    {"total_images": total_images},
                )

        # 이미지 품질 권장사항
        if total_images < 3:
            result.add_warning(
                "images",
                "상품 이미지가 3개 미만입니다. 더 많은 이미지를 추가하면 판매율이 향상됩니다",
            )

    def _validate_stock_status(self, product: StandardProduct, result: ValidationResult):
        """재고 및 상태 검증"""
        if product.stock is not None and product.stock < 0:
            result.add_error("stock", "재고 수량은 0 이상이어야 합니다")

        if product.stock == 0 and product.status == ProductStatus.ACTIVE:
            result.add_warning(
                "stock",
                "재고가 없는데 상태가 활성입니다. 상태를 SOLDOUT으로 변경하는 것을 권장합니다",
            )

        if product.stock and product.stock > 0 and product.status == ProductStatus.OUT_OF_STOCK:
            result.add_warning(
                "status",
                "재고가 있는데 상태가 품절입니다. 상태를 ACTIVE로 변경하는 것을 권장합니다",
            )

    def _validate_category(self, product: StandardProduct, result: ValidationResult):
        """카테고리 검증"""
        if not product.category_code and not product.category_name:
            result.add_warning("category", "카테고리 정보가 없습니다")

        if product.category_code and not product.category_name:
            result.add_info("category", "카테고리명이 없습니다. 자동 매핑이 필요할 수 있습니다")

    def _calculate_quality_score(self, result: ValidationResult) -> float:
        """품질 점수 계산"""
        score = 1.0

        # 오류당 20% 감점
        score -= len(result.errors) * 0.2

        # 경고당 5% 감점
        score -= len(result.warnings) * 0.05

        # 최소 점수는 0
        return max(0.0, score)

    def validate_bulk(
        self, products: List[StandardProduct], marketplace: Optional[str] = None
    ) -> Dict[str, ValidationResult]:
        """여러 상품 일괄 검증"""
        results = {}

        for product in products:
            results[product.id] = self.validate_product(product, marketplace)

        return results

    def get_validation_summary(self, results: Dict[str, ValidationResult]) -> Dict[str, Any]:
        """검증 결과 요약"""
        total = len(results)
        valid = sum(1 for r in results.values() if r.is_valid)
        total_errors = sum(len(r.errors) for r in results.values())
        total_warnings = sum(len(r.warnings) for r in results.values())
        avg_score = sum(r.score for r in results.values()) / total if total > 0 else 0

        return {
            "total_products": total,
            "valid_products": valid,
            "invalid_products": total - valid,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "average_quality_score": avg_score,
            "validation_rate": valid / total if total > 0 else 0,
        }
