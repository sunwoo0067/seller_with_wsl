"""
도매매 상품 데이터 변환기
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional

from loguru import logger

from dropshipping.models.product import StandardProduct, ProductImage, ProductOption, OptionType, ProductStatus
from dropshipping.transformers.base import BaseTransformer

class DomemeTransformer(BaseTransformer):
    """도매매 데이터를 StandardProduct 모델로 변환"""

    def __init__(self) -> None:
        self.supplier_id = "domeme"
        self._errors: List[Dict[str, Any]] = []

    def to_standard(self, data: Dict[str, Any]) -> Optional[StandardProduct]:
        """도매매 API 응답을 StandardProduct 모델로 변환"""
        try:
            # 필수 필드 확인 (Mock 데이터 필드명 고려)
            product_no = data.get("productNo") or data.get("productNm")
            product_name = data.get("productName") or data.get("productNm")
            price = data.get("price") or data.get("supplyPrice")
            
            if not all([product_no, product_name, price]):
                logger.warning(f"필수 필드가 누락되었습니다: {data.get('productNo', data.get('productNm'))}")
                return None

            # 가격 정보 처리
            cost = self._to_decimal(price)
            list_price = self._to_decimal(data.get("consumerPrice", 0))
            if list_price == 0:
                list_price = cost

            # 상태 결정
            status = self._get_status(data)

            # 카테고리 정보
            category_code, category_name, category_path = self._extract_category(data)

            # 이미지
            images = self._extract_images(data)

            # 옵션
            options = self._extract_options(data)

            # 표준 상품 모델 생성
            product = StandardProduct(
                id=f"domeme_{product_no}",
                supplier_id="domeme",
                supplier_product_id=str(product_no),
                name=product_name,
                brand=data.get("brandName") or data.get("brandNm"),
                manufacturer=data.get("manufacturer") or data.get("makerNm"),
                origin=data.get("origin"),
                cost=cost,
                price=cost,  # 초기 가격은 원가와 동일하게 설정
                list_price=list_price,
                stock=int(data.get("stockQuantity", data.get("stockQty", 0))),
                status=status,
                category_code=category_code,
                category_name=category_name,
                category_path=category_path,
                images=images,
                options=options,
                attributes=self._extract_attributes(data),
                description=data.get("description", ""),
                shipping_fee=self._to_decimal(data.get("deliveryPrice", 0)),
                shipping_method=data.get("deliveryType", "택배"),
                raw_data=data
            )

            return product

        except Exception as e:
            logger.error(f"도매매 데이터 변환 실패 ({data.get('productNo')}): {str(e)}")
            return None

    def _to_decimal(self, value: Any) -> Decimal:
        """안전하게 Decimal로 변환"""
        try:
            return Decimal(value)
        except (ValueError, TypeError):
            return Decimal(0)

    def _get_status(self, data: Dict[str, Any]) -> ProductStatus:
        """상품 상태 결정"""
        if data.get("isSoldOut") == "Y":
            return ProductStatus.SOLD_OUT
        if data.get("isStopSelling") == "Y":
            return ProductStatus.DISCONTINUED
        if int(data.get("stockQuantity", 0)) <= 0:
            return ProductStatus.OUT_OF_STOCK
        return ProductStatus.ACTIVE

    def _extract_category(self, data: Dict[str, Any]) -> tuple:
        """카테고리 정보 추출"""
        category_code = data.get("categoryCode")
        category_path_names = []
        for i in range(1, 5):
            cat_name = data.get(f"category{i}Name")
            if cat_name:
                category_path_names.append(cat_name)
        
        category_name = category_path_names[-1] if category_path_names else None
        return category_code, category_name, category_path_names

    def _extract_images(self, data: Dict[str, Any]) -> List[ProductImage]:
        """이미지 정보 추출"""
        images = []
        # 메인 이미지
        if data.get("mainImage"): 
            images.append(ProductImage(url=data["mainImage"], is_main=True, order=0))
        
        # 추가 이미지
        for i in range(1, 11):
            img_url = data.get(f"addImg{i}")
            if img_url:
                images.append(ProductImage(url=img_url, is_main=False, order=i))
        
        return images

    def _extract_options(self, data: Dict[str, Any]) -> List[ProductOption]:
        """옵션 정보 추출"""
        options = []
        # 도매매는 옵션을 단일 문자열로 제공하는 경우가 많음
        # 예: "색상:블랙,레드|사이즈:S,M,L"
        option_str = data.get("option")
        if not option_str:
            return []

        try:
            # 옵션 그룹 분리
            option_groups = option_str.split('|')
            for group in option_groups:
                parts = group.split(':')
                if len(parts) == 2:
                    name, values_str = parts
                    values = values_str.split(',')
                    options.append(
                        ProductOption(
                            name=name.strip(),
                            type=OptionType.SELECT,
                            values=[v.strip() for v in values],
                            required=True
                        )
                    )
        except Exception as e:
            logger.warning(f"옵션 파싱 실패 ({data.get('productNo')}): {option_str}, error: {e}")

        return options

    def _extract_attributes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """추가 속성 추출"""
        return {
            "delivery_type": data.get("deliveryType"),
            "delivery_fee": self._to_decimal(data.get("deliveryFee", 0)),
            "tax_type": data.get("taxType"),
            "adult_only": data.get("isAdultOnly") == "Y",
            "model_name": data.get("modelName"),
        }