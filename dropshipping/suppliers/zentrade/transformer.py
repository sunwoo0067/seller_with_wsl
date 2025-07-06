"""
젠트레이드 상품 변환기
파싱된 데이터를 표준 상품 모델로 변환
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal

from dropshipping.models.product import (
    StandardProduct,
    ProductImage,
    ProductOption,
    ProductVariant,
    ShippingInfo,
    ProductStatus,
)
from dropshipping.transformers.base import BaseTransformer
from dropshipping.monitoring.logger import get_logger

logger = get_logger(__name__)


class ZentradeTransformer(BaseTransformer):
    """젠트레이드 상품 변환기"""

    def __init__(self):
        self.supplier_id = "zentrade"
        self._errors = []

    def to_standard(self, raw_product: Dict[str, Any]) -> Optional[StandardProduct]:
        """원본 상품을 표준 형식으로 변환

        Args:
            raw_product: 파싱된 젠트레이드 상품 데이터

        Returns:
            표준 상품 모델 또는 None
        """
        try:
            # 필수 필드 검증
            if not raw_product.get("id") or not raw_product.get("name"):
                logger.warning(f"필수 필드 누락: {raw_product.get('id')}")
                return None

            # 상태 변환
            status_map = {
                "active": ProductStatus.ACTIVE,
                "inactive": ProductStatus.INACTIVE,
                "soldout": ProductStatus.OUT_OF_STOCK,
            }
            status = status_map.get(raw_product.get("status", "active"), ProductStatus.ACTIVE)

            # 가격 정보
            base_price = float(raw_product.get("price", 0))

            # 판매가 계산 (30% 마진)
            selling_price = self._calculate_selling_price(base_price)

            # 이미지 처리
            images = self._process_images(raw_product.get("images", []))

            # 옵션 처리
            options_data = raw_product.get("options", {})
            options, variants = self._process_options(options_data)

            # 배송 정보
            shipping_info = self._create_shipping_info(raw_product)

            # 재고 수량
            stock_quantity = int(raw_product.get("stock", 0))

            # 상품 설명
            description = self._create_description(raw_product)

            # 표준 상품 생성
            return StandardProduct(
                id=f"zentrade_{raw_product['id']}",
                supplier_id="zentrade",
                supplier_product_id=raw_product["id"],
                name=self._clean_product_name(raw_product["name"]),
                description=description,
                brand=raw_product.get("brand", ""),
                manufacturer=raw_product.get("brand", ""),
                origin="",  # 젠트레이드는 원산지 정보가 없을 수 있음
                category_code=raw_product.get("category", ""),
                category_name=raw_product.get("category", ""),
                cost=Decimal(str(base_price)),
                price=Decimal(str(selling_price)),
                list_price=None,  # 정가 정보 없음
                stock=stock_quantity,
                status=status,
                images=images,
                options=options,
                variants=variants,
                shipping_fee=Decimal(str(shipping_info.fee)),
                is_free_shipping=(shipping_info.method == "무료배송"),
                shipping_method=shipping_info.method,
                attributes={
                    "model": raw_product.get("model", ""),
                    "shipping_info": shipping_info.model_dump(),
                    "original_status": raw_product.get("status", ""),
                },
                tags=[],
                raw_data=raw_product.get("raw_data", raw_product),
            )

        except Exception as e:
            logger.error(f"상품 변환 실패 [{raw_product.get('id')}]: {str(e)}")
            return None

    def _calculate_selling_price(self, base_price: float) -> float:
        """판매가 계산

        Args:
            base_price: 기준 가격

        Returns:
            계산된 판매가
        """
        # 30% 마진 적용
        price = base_price * 1.3

        # 100원 단위로 반올림
        return round(price / 100) * 100

    def _process_images(self, images: List[str]) -> List[ProductImage]:
        """이미지 URL 목록을 ProductImage 객체로 변환

        Args:
            images: 이미지 URL 목록

        Returns:
            ProductImage 객체 목록
        """
        product_images = []

        for idx, url in enumerate(images):
            if url and isinstance(url, str):
                # URL이 상대경로인 경우 절대경로로 변환
                if not url.startswith(("http://", "https://")):
                    # 젠트레이드 기본 도메인 추가
                    url = f"https://www.zentrade.co.kr{url}"

                product_images.append(ProductImage(url=url, is_main=(idx == 0), order=idx))

        return product_images

    def _process_options(
        self, options_data: Dict[str, Any]
    ) -> tuple[List[ProductOption], List[ProductVariant]]:
        """옵션 정보를 표준 형식으로 변환

        Args:
            options_data: 파싱된 옵션 데이터

        Returns:
            (ProductOption 목록, ProductVariant 목록) 튜플
        """
        product_options = []
        variants = []

        # 옵션 데이터가 딕셔너리 형태인 경우
        if isinstance(options_data, dict):
            # 옵션 그룹 정보
            groups = options_data.get("groups", [])
            for group in groups:
                product_options.append(
                    ProductOption(name=group["name"], values=group["values"], required=True)
                )

            # 개별 옵션 아이템 (변형 상품)
            items = options_data.get("items", [])
            for idx, item in enumerate(items):
                variant_options = {item["name"]: item["value"]}

                variants.append(
                    ProductVariant(
                        sku=item.get("sku", f"ZT-{idx+1}"),
                        name=f"{item['name']}: {item['value']}",
                        options=variant_options,
                        stock=item.get("stock", 0),
                        attributes={"original_price": item.get("price", 0)},
                    )
                )

        # 옵션 데이터가 리스트 형태인 경우 (레거시)
        elif isinstance(options_data, list):
            option_groups = {}

            for idx, opt in enumerate(options_data):
                name = opt.get("name", "")
                value = opt.get("value", "")

                if not name or not value:
                    continue

                # 옵션 그룹화
                if name not in option_groups:
                    option_groups[name] = set()
                option_groups[name].add(value)

                # 변형 상품 생성
                variants.append(
                    ProductVariant(
                        sku=f"ZT-{idx+1}",
                        name=f"{name}: {value}",
                        options={name: value},
                        stock=opt.get("stock", 0),
                    )
                )

            # ProductOption 생성
            for opt_name, opt_values in option_groups.items():
                product_options.append(
                    ProductOption(name=opt_name, values=list(opt_values), required=True)
                )

        return product_options, variants

    def _create_shipping_info(self, raw_product: Dict[str, Any]) -> ShippingInfo:
        """배송 정보 생성

        Args:
            raw_product: 원본 상품 데이터

        Returns:
            배송 정보 객체
        """
        shipping_fee = float(raw_product.get("shipping_fee", 0))
        shipping_method = raw_product.get("shipping_method", "기본배송")
        free_condition = float(raw_product.get("shipping_free_condition", 0))

        # 배송 방법 결정
        if shipping_fee == 0:
            method = "무료배송"
        elif free_condition > 0:
            method = "조건부 무료배송"
        else:
            method = shipping_method

        return ShippingInfo(
            method=method,
            fee=shipping_fee,
            estimated_days_min=2,
            estimated_days_max=3,
            free_shipping_minimum=free_condition if free_condition > 0 else None,
        )

    def _create_description(self, raw_product: Dict[str, Any]) -> str:
        """상품 설명 생성

        Args:
            raw_product: 원본 상품 데이터

        Returns:
            생성된 설명
        """
        description = raw_product.get("description", "")

        # 추가 정보 포함
        parts = []

        if description:
            parts.append(description)

        if raw_product.get("model"):
            parts.append(f"\n모델명: {raw_product['model']}")

        if raw_product.get("brand"):
            parts.append(f"브랜드: {raw_product['brand']}")

        return "\n".join(parts)

    def _clean_product_name(self, name: str) -> str:
        """상품명 정리

        Args:
            name: 원본 상품명

        Returns:
            정리된 상품명
        """
        # 불필요한 공백 제거
        name = " ".join(name.split())

        # 특수문자 정리
        name = name.replace("™", "").replace("®", "")

        # 길이 제한 (80자)
        if len(name) > 80:
            name = name[:77] + "..."

        return name
