"""
도매매 상품 데이터 변환기
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

from loguru import logger

from dropshipping.models.product import (
    OptionType,
    ProductImage,
    ProductOption,
    ProductStatus,
    StandardProduct,
)
from dropshipping.transformers.base import BaseTransformer


class DomemeTransformer(BaseTransformer):
    """도매매 데이터를 StandardProduct 모델로 변환"""

    def __init__(self) -> None:
        self.supplier_id = "domeme"
        self._errors: List[Dict[str, Any]] = []

    def parse_xml_to_dict(self, xml_string: str) -> Dict[str, Any]:
        """XML 문자열을 딕셔너리로 변환"""
        try:
            root = ET.fromstring(xml_string)
            return self._element_to_dict(root)
        except Exception as e:
            logger.error(f"XML 파싱 에러: {e}")
            return {}

    def _element_to_dict(self, element) -> Dict[str, Any]:
        """XML 엘리먼트를 딕셔너리로 변환"""
        result = {}

        # 엘리먼트의 텍스트가 있으면 추가
        if element.text and element.text.strip():
            if len(element) == 0:  # 자식 노드가 없으면
                return element.text.strip()
            else:
                result["_text"] = element.text.strip()

        # 속성이 있으면 추가
        if element.attrib:
            result.update(element.attrib)

        # 자식 엘리먼트 처리
        for child in element:
            child_data = self._element_to_dict(child)
            if child.tag in result:
                # 이미 같은 태그가 있으면 리스트로 변환
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data

        return result

    def to_standard(self, data: Dict[str, Any]) -> Optional[StandardProduct]:
        """도매매 API 응답을 StandardProduct 모델로 변환"""
        try:
            # 필수 필드 확인
            product_no = data.get("productNo")
            product_name = data.get("productNm") or data.get("productName")
            price = data.get("supplyPrice") or data.get("price")

            if not all([product_no, product_name, price]):
                logger.warning(
                    f"필수 필드가 누락되었습니다: {data.get('productNo', data.get('productNm'))}"
                )
                return None

            # 가격 정보 처리
            cost = self._to_decimal(price)
            sale_price = self._to_decimal(data.get("salePrice", price))  # 판매가
            list_price = self._to_decimal(data.get("consumerPrice", 0))  # 소비자가
            if list_price == 0:
                list_price = sale_price

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
                price=sale_price,  # 판매가 사용
                list_price=list_price,
                stock=int(data.get("stockQty", data.get("stockQuantity", 0))),
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
                raw_data=data,
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
        # productStatus가 N인 경우 비활성
        if data.get("productStatus") == "N":
            return ProductStatus.INACTIVE
        if data.get("isSoldOut") == "Y":
            return ProductStatus.SOLD_OUT
        if data.get("isStopSelling") == "Y":
            return ProductStatus.DISCONTINUED
        # stockQty 필드명도 지원
        stock = int(data.get("stockQty", data.get("stockQuantity", 0)))
        if stock <= 0:
            return ProductStatus.OUT_OF_STOCK
        return ProductStatus.ACTIVE

    def _extract_category(self, data: Dict[str, Any]) -> tuple:
        """카테고리 정보 추출"""
        # category1, categoryNm1 형식도 지원
        category_code = data.get("categoryCode") or data.get("category1")
        category_path_names = []

        # categoryNm1, categoryNm2... 형식 지원
        for i in range(1, 5):
            cat_name = data.get(f"categoryNm{i}") or data.get(f"category{i}Name")
            if cat_name:
                category_path_names.append(cat_name)

        category_name = category_path_names[-1] if category_path_names else None
        return category_code, category_name, category_path_names

    def _extract_images(self, data: Dict[str, Any]) -> List[ProductImage]:
        """이미지 정보 추출"""
        images = []
        # 메인 이미지 (mainImg 또는 mainImage)
        main_img = data.get("mainImg") or data.get("mainImage")
        if main_img:
            images.append(ProductImage(url=main_img, is_main=True, order=0))

        # 추가 이미지
        for i in range(1, 11):
            img_url = data.get(f"addImg{i}")
            if img_url:
                images.append(ProductImage(url=img_url, is_main=False, order=i))

        return images

    def _extract_options(self, data: Dict[str, Any]) -> List[ProductOption]:
        """옵션 정보 추출"""
        options = []

        # option1Nm/option1Value, option2Nm/option2Value 형식 처리
        for i in range(1, 10):
            option_name = data.get(f"option{i}Nm")
            option_values = data.get(f"option{i}Value")

            if option_name and option_values:
                # 쉼표로 구분된 값들을 리스트로 변환
                values = [v.strip() for v in option_values.split(",")]
                options.append(
                    ProductOption(
                        name=option_name,
                        type=OptionType.SELECT,
                        values=values,
                        required=True,
                    )
                )

        # 기존 option 문자열 형식도 지원
        # 예: "색상:블랙,레드|사이즈:S,M,L"
        option_str = data.get("option")
        if option_str and not options:  # 위에서 옵션을 찾지 못한 경우만
            try:
                # 옵션 그룹 분리
                option_groups = option_str.split("|")
                for group in option_groups:
                    parts = group.split(":")
                    if len(parts) == 2:
                        name, values_str = parts
                        values = values_str.split(",")
                        options.append(
                            ProductOption(
                                name=name.strip(),
                                type=OptionType.SELECT,
                                values=[v.strip() for v in values],
                                required=True,
                            )
                        )
            except Exception as e:
                logger.warning(
                    f"옵션 파싱 실패 ({data.get('productNo')}): {option_str}, error: {e}"
                )

        return options

    def _extract_attributes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """추가 속성 추출"""
        return {
            "delivery_type": data.get("deliveryType"),
            "delivery_fee": self._to_decimal(
                data.get("deliveryPrice") or data.get("deliveryFee", 0)
            ),
            "tax_type": data.get("taxType"),
            "adult_only": data.get("isAdultOnly") == "Y",
            "model_name": data.get("modelName"),
            "manufacturer": data.get("makerNm"),
            "origin": data.get("origin"),
        }

    def from_standard(self, product: StandardProduct) -> Dict[str, Any]:
        """StandardProduct를 도매매 형식으로 변환 (현재 미구현)"""
        raise NotImplementedError("도매매 역변환은 현재 지원하지 않습니다")

    def _safe_int(self, value: Any, default: int = 0) -> int:
        """안전하게 정수로 변환"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_str(self, value: Any, default: str = "") -> str:
        """안전하게 문자열로 변환"""
        try:
            return str(value)
        except (ValueError, TypeError):
            return default

    def _get_value(self, data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
        """여러 키 중 첫 번째로 존재하는 값 반환"""
        for key in keys:
            if key in data:
                return data[key]
        return default

    # Public 메서드 (테스트용)
    def safe_int(self, value: Any, default: int = 0) -> int:
        """안전하게 정수로 변환 (public)"""
        return self._safe_int(value, default)

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """안전하게 실수로 변환"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def safe_str(self, value: Any, default: str = "") -> str:
        """안전하게 문자열로 변환 (public)"""
        if value is None:
            return default
        result = self._safe_str(value, default)
        return result.strip() if result else result

    def get_value(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """중첩된 딕셔너리에서 값 추출 (dot notation 지원)"""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
