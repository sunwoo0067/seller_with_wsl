"""
도매매(Domeme) 데이터 변환기
XML 응답을 StandardProduct로 변환
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET

from dropshipping.models.product import (
    StandardProduct,
    ProductImage,
    ProductOption,
    ProductStatus,
    OptionType,
)
from dropshipping.transformers.base import DictTransformer, TransformError


class DomemeTransformer(DictTransformer):
    """도매매 상품 데이터 변환기"""

    def __init__(self):
        super().__init__("domeme")

    def parse_xml_to_dict(self, xml_str: str) -> Dict[str, Any]:
        """XML 문자열을 딕셔너리로 변환"""
        try:
            root = ET.fromstring(xml_str)
            return self._element_to_dict(root)
        except ET.ParseError as e:
            raise TransformError(f"XML 파싱 오류: {str(e)}")

    def _element_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """XML 요소를 딕셔너리로 재귀 변환"""
        result = {}

        # 속성 처리
        if element.attrib:
            result.update(element.attrib)

        # 자식 요소 처리
        for child in element:
            child_data = self._element_to_dict(child)

            # 동일한 태그가 여러 개인 경우 리스트로 처리
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data

        # 텍스트 내용 처리
        if element.text and element.text.strip():
            if result:
                result["_text"] = element.text.strip()
            else:
                return element.text.strip()

        return result or ""

    def to_standard(self, raw_data: Dict[str, Any]) -> StandardProduct:
        """도매매 데이터를 표준 형식으로 변환"""
        try:
            # 상품 ID 생성
            product_no = self.safe_str(raw_data.get("productNo"))
            if not product_no:
                raise TransformError("상품 번호가 없습니다")

            product_id = f"domeme_{product_no}"

            # 기본 정보 추출
            name = self.safe_str(raw_data.get("productNm"))
            if not name:
                raise TransformError("상품명이 없습니다")

            # 가격 정보
            cost = Decimal(str(self.safe_float(raw_data.get("supplyPrice", 0))))
            price = Decimal(str(self.safe_float(raw_data.get("salePrice", cost * Decimal("1.3")))))
            list_price = Decimal(str(self.safe_float(raw_data.get("consumerPrice", price))))

            # 재고 및 상태
            stock = self.safe_int(raw_data.get("stockQty", 0))
            status = self._get_status(raw_data.get("productStatus", "Y"), stock)

            # 카테고리
            category_code = self.safe_str(raw_data.get("category1"))
            category_name = self.safe_str(raw_data.get("categoryNm1"))
            category_path = self._build_category_path(raw_data)

            # 이미지 처리
            images = self._extract_images(raw_data)

            # 옵션 처리
            options = self._extract_options(raw_data)

            # 배송 정보
            shipping_fee = Decimal(str(self.safe_float(raw_data.get("deliveryPrice", 0))))
            is_free_shipping = shipping_fee == 0

            # 추가 속성
            attributes = {
                "model_no": self.safe_str(raw_data.get("modelNo")),
                "model_nm": self.safe_str(raw_data.get("modelNm")),
                "material": self.safe_str(raw_data.get("material")),
                "size": self.safe_str(raw_data.get("size")),
                "weight": self.safe_str(raw_data.get("weight")),
            }
            # 빈 값 제거
            attributes = {k: v for k, v in attributes.items() if v}

            # StandardProduct 생성
            return StandardProduct(
                id=product_id,
                supplier_id=self.supplier_id,
                supplier_product_id=product_no,
                name=name,
                description=self.safe_str(raw_data.get("description")),
                brand=self.safe_str(raw_data.get("brandNm")),
                manufacturer=self.safe_str(raw_data.get("makerNm")),
                origin=self.safe_str(raw_data.get("origin")),
                category_code=category_code,
                category_name=category_name,
                category_path=category_path,
                cost=cost,
                price=price,
                list_price=list_price,
                stock=stock,
                status=status,
                images=images,
                options=options,
                shipping_fee=shipping_fee,
                is_free_shipping=is_free_shipping,
                shipping_method=self.safe_str(raw_data.get("deliveryType")),
                attributes=attributes,
                raw_data=raw_data,
            )

        except (KeyError, ValueError) as e:
            raise TransformError(f"데이터 변환 오류: {str(e)}")

    def from_standard(self, product: StandardProduct) -> Dict[str, Any]:
        """표준 형식을 도매매 형식으로 변환 (업로드용)"""
        # 도매매는 읽기 전용 API이므로 구현하지 않음
        raise NotImplementedError("도매매는 상품 업로드를 지원하지 않습니다")

    def _get_status(self, status_code: str, stock: int) -> ProductStatus:
        """상태 코드 변환"""
        if stock == 0:
            return ProductStatus.SOLDOUT
        elif status_code == "Y":
            return ProductStatus.ACTIVE
        else:
            return ProductStatus.INACTIVE

    def _build_category_path(self, data: Dict[str, Any]) -> List[str]:
        """카테고리 경로 구성"""
        path = []
        for i in range(1, 5):  # 최대 4단계 카테고리
            cat_name = self.safe_str(data.get(f"categoryNm{i}"))
            if cat_name:
                path.append(cat_name)
            else:
                break
        return path

    def _extract_images(self, data: Dict[str, Any]) -> List[ProductImage]:
        """이미지 정보 추출"""
        images = []

        # 메인 이미지
        main_img = self.safe_str(data.get("mainImg"))
        if main_img:
            images.append(ProductImage(url=main_img, is_main=True, order=0))

        # 추가 이미지
        for i in range(1, 11):  # 최대 10개 추가 이미지
            img_url = self.safe_str(data.get(f"addImg{i}"))
            if img_url:
                images.append(ProductImage(url=img_url, is_main=False, order=i))

        return images

    def _extract_options(self, data: Dict[str, Any]) -> List[ProductOption]:
        """옵션 정보 추출"""
        options = []

        # 옵션1: 주로 색상
        option1_name = self.safe_str(data.get("option1Nm"))
        option1_values = self.safe_str(data.get("option1Value"))
        if option1_name and option1_values:
            values = [v.strip() for v in option1_values.split(",")]
            options.append(
                ProductOption(
                    name=option1_name, type=OptionType.SELECT, values=values, required=True
                )
            )

        # 옵션2: 주로 사이즈
        option2_name = self.safe_str(data.get("option2Nm"))
        option2_values = self.safe_str(data.get("option2Value"))
        if option2_name and option2_values:
            values = [v.strip() for v in option2_values.split(",")]
            options.append(
                ProductOption(
                    name=option2_name, type=OptionType.SELECT, values=values, required=True
                )
            )

        return options
