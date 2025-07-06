"""
11번가 OpenAPI 업로더
11번가 OpenAPI를 통한 상품 업로드
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from dropshipping.config import ElevenstConfig
from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import BaseUploader, MarketplaceType


class ElevenstUploader(BaseUploader):
    """11번가 업로더"""

    def __init__(self, storage: BaseStorage, config: ElevenstConfig):
        super().__init__(MarketplaceType.ELEVENST, storage, config)

        # API 설정
        self.seller_id = self.config.seller_id
        self.test_mode = self.config.test_mode
        self.base_url = self.config.base_url
        self.category_mapping = self.config.category_mapping

        # HTTP 클라이언트
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"openapikey": self.config.api_key},
            timeout=30.0,
        )

    async def upload_product(self, product: StandardProduct) -> Dict[str, Any]:
        """상품을 마켓플레이스에 업로드합니다."""
        is_valid, error_message = await self.validate_product(product)
        if not is_valid:
            logger.error(f"상품 검증 실패: {error_message}")
            return {"success": False, "error": f"상품 검증 실패: {error_message}"}

        product_data = await self.transform_product(product)
        result = await self.upload_single(product_data)
        return result

    async def update_stock(self, marketplace_product_id: str, stock: int) -> bool:
        """재고 수정 (미구현)"""
        raise NotImplementedError("11번가 재고 수정 기능은 아직 구현되지 않았습니다.")

    async def update_price(self, marketplace_product_id: str, price: float) -> bool:
        """가격 수정 (미구현)"""
        raise NotImplementedError("11번가 가격 수정 기능은 아직 구현되지 않았습니다.")

    async def check_upload_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """상품 업로드 상태 확인 (미구현)"""
        raise NotImplementedError("11번가 상품 상태 확인 기능은 아직 구현되지 않았습니다.")

    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        """상품 검증"""
        errors = []

        # 필수 필드 검증
        if not product.name:
            errors.append("상품명 누락")
        elif len(product.name) > 200:
            errors.append("상품명이 너무 깁니다 (최대 200자)")

        if not product.price or product.price < 100:
            errors.append("판매가격이 너무 낮습니다 (최소 100원)")

        if not product.images or len(product.images) == 0:
            errors.append("상품 이미지가 없습니다")

        # 카테고리 확인
        if product.category_name not in self.category_mapping:
            errors.append(f"지원하지 않는 카테고리: {product.category_name}")

        # 상품 설명 길이 확인
        if product.description and len(product.description) > 40000:
            errors.append("상품 설명이 너무 깁니다 (최대 40000자)")

        if errors:
            return False, "; ".join(errors)

        return True, None

    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """상품 데이터 변환 (XML 형식)"""

        # 11번가 XML 구조
        product_data = {
            "Product": {
                "prdNo": "",  # 신규 상품은 빈 값
                "dispCtgrNo": self.category_mapping.get(product.category_name),
                "prdNm": product.name[:200],
                "brand": product.brand or "기타",
                "rmaterialTypCd": "05",  # 상품재질: 기타
                "orgnTypCd": "03",  # 원산지: 국산
                "orgnTypDtlsCd": "01",  # 세부원산지: 한국
                "stkQty": str(product.stock),
                "dlvCstInstBasiCd": "02",  # 배송비 결제: 선결제
                "dlvCstPayTypCd": "03",  # 배송비 유형: 조건부무료
                "dlvCst1": str(self.config.delivery_cost),
                "dlvCst2": str(self.config.free_shipping_threshold),
                "exchDlvCst": str(self.config.exchange_delivery_cost),
                "rtngDlvCst": str(self.config.return_delivery_cost),
                "dlvClf": "01",  # 배송분류: 국내배송
                "dlvEtprsCd": self.config.delivery_company_code,
                "productPrdImage": [
                    {
                        "prdImage01": str(product.images[0].url) if len(product.images) > 0 else "",
                        "prdImage02": str(product.images[1].url) if len(product.images) > 1 else "",
                        "prdImage03": str(product.images[2].url) if len(product.images) > 2 else "",
                        "prdImage04": str(product.images[3].url) if len(product.images) > 3 else "",
                    }
                ],
                "htmlDetail": self._create_html_detail(product),
                "selPrc": str(int(product.price)),  # 판매가
                "prdSelQty": "1",  # 판매수량
                "dscAmtPercnt": "10",  # 할인율 10%
                "validateDay": "0",  # 유효기간 무제한
                "nIntfcGrpNo": "",  # 인터페이스 그룹번호
                "dispCtgrStatCd": "01",  # 카테고리 상태: 정상
                "paidSelPrc": str(int(product.price * Decimal("0.9"))),  # 할인가
                "sellerPrdCd": product.id,  # 판매자 상품코드
                "optSelectYn": "Y" if product.variants else "N",  # 옵션 여부
                "optMixYn": "N",  # 조합형 옵션 여부
                "tmpltSeq": "0",  # 템플릿 번호
                "prdTypCd": "01",  # 상품유형: 일반
                "minorSelCnYn": "N",  # 미성년자 구매 가능
                "saleStartDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "saleEndDate": "2099-12-31 23:59:59",
            }
        }

        # 옵션 정보 추가
        if product.variants:
            product_data["Product"]["productOption"] = self._create_options(product)

        return product_data

    def _create_html_detail(self, product: StandardProduct) -> str:
        """HTML 상세 설명 생성"""
        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2>{product.name}</h2>
            <div>{product.description or '상품 상세 설명'}</div>
            
            <h3>상품 정보</h3>
            <ul>
                <li>브랜드: {product.brand or '기타'}</li>
                <li>원산지: 한국</li>
                <li>제조사: {product.attributes.get('manufacturer', '제조사 정보 없음')}</li>
            </ul>
            
            <h3>배송 정보</h3>
            <ul>
                <li>배송비: 2,500원 (3만원 이상 무료배송)</li>
                <li>배송기간: 2-3일</li>
                <li>택배사: CJ대한통운</li>
            </ul>
            
            <h3>교환/반품 안내</h3>
            <p>상품 수령 후 7일 이내 교환/반품 가능합니다.</p>
        </div>
        """
        return html

    def _create_options(self, product: StandardProduct) -> List[Dict[str, Any]]:
        """옵션 정보 생성"""
        options = []

        for i, variant in enumerate(product.variants):
            option = {
                "optionSeq": str(i + 1),
                "optionName": variant.name,
                "optionValue": variant.option_value,
                "optionPrice": "0",  # 옵션 추가금 없음
                "optionQty": str(variant.stock),
                "optionUseYn": "Y",
            }
            options.append(option)

        return options

    def _dict_to_xml(self, data: Dict[str, Any], root_name: str = "Product") -> str:
        """딕셔너리를 XML로 변환"""
        root = ET.Element(root_name)

        def build_xml(element, data):
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, list):
                        for item in value:
                            sub_elem = ET.SubElement(element, key)
                            build_xml(sub_elem, item)
                    else:
                        sub_elem = ET.SubElement(element, key)
                        if isinstance(value, dict):
                            build_xml(sub_elem, value)
                        else:
                            sub_elem.text = str(value) if value is not None else ""
            else:
                element.text = str(data) if data is not None else ""

        build_xml(root, data["Product"])

        # XML 문자열로 변환
        xml_str = ET.tostring(root, encoding="unicode")

        # XML 선언 추가
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """단일 상품 업로드"""
        try:
            # XML 변환
            xml_data = self._dict_to_xml(product_data)

            # API 호출
            response = await self._api_request(
                "POST",
                "/prodservices/product",
                content=xml_data,
                headers={"Content-Type": "text/xml;charset=UTF-8"},
            )

            # XML 응답 파싱
            root = ET.fromstring(response.text)

            result_code = root.find(".//resultCode")
            result_msg = root.find(".//resultMsg")
            product_no = root.find(".//prdNo")

            if result_code is not None and result_code.text == "200":
                return {
                    "success": True,
                    "product_id": product_no.text if product_no is not None else None,
                    "message": result_msg.text if result_msg is not None else "성공",
                }
            else:
                return {
                    "success": False,
                    "error": result_msg.text if result_msg is not None else "업로드 실패",
                    "code": result_code.text if result_code is not None else None,
                }

        except Exception as e:
            logger.error(f"11번가 업로드 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    async def update_single(
        self, marketplace_product_id: str, product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """단일 상품 수정"""
        try:
            # 상품번호 추가
            product_data["Product"]["prdNo"] = marketplace_product_id

            # XML 변환
            xml_data = self._dict_to_xml(product_data)

            # API 호출
            response = await self._api_request(
                "PUT",
                "/prodservices/product",
                content=xml_data,
                headers={"Content-Type": "text/xml;charset=UTF-8"},
            )

            # XML 응답 파싱
            root = ET.fromstring(response.text)

            result_code = root.find(".//resultCode")
            result_msg = root.find(".//resultMsg")

            if result_code is not None and result_code.text == "200":
                return {
                    "success": True,
                    "product_id": marketplace_product_id,
                    "message": result_msg.text if result_msg is not None else "성공",
                }
            else:
                return {
                    "success": False,
                    "error": result_msg.text if result_msg is not None else "수정 실패",
                    "code": result_code.text if result_code is not None else None,
                }

        except Exception as e:
            logger.error(f"11번가 수정 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """상품 상태 확인"""
        try:
            response = await self._api_request(
                "GET", f"/prodservices/product/{marketplace_product_id}"
            )

            # XML 응답 파싱
            root = ET.fromstring(response.text)

            result_code = root.find(".//resultCode")
            result_msg = root.find(".//resultMsg")
            status = root.find(".//productStatCd")

            if result_code is not None and result_code.text == "200":
                return {
                    "success": True,
                    "status": status.text if status is not None else None,
                    "status_name": self._get_status_name(status.text if status is not None else ""),
                    "product_data": self._xml_to_dict(root),
                }
            else:
                return {
                    "success": False,
                    "error": result_msg.text if result_msg is not None else "조회 실패",
                }

        except Exception as e:
            logger.error(f"11번가 상태 확인 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _get_status_name(self, status_code: str) -> str:
        """상태 코드를 이름으로 변환"""
        status_mapping = {
            "101": "판매대기",
            "102": "판매불가",
            "103": "판매중",
            "104": "판매중지",
            "105": "품절",
        }
        return status_mapping.get(status_code, "알 수 없음")

    def _xml_to_dict(self, element) -> Dict[str, Any]:
        """XML을 딕셔너리로 변환"""
        result = {}

        for child in element:
            if len(child) == 0:
                result[child.tag] = child.text
            else:
                if child.tag not in result:
                    result[child.tag] = []
                result[child.tag].append(self._xml_to_dict(child))

        return result

    async def _api_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """11번가 API 요청"""

        # 인증 헤더
        headers = kwargs.get("headers", {})
        headers["openapikey"] = self.api_key
        kwargs["headers"] = headers

        # 요청 URL
        url = self.base_url + path

        # API 호출
        logger.debug(f"11번가 API 호출: {method} {url}")

        response = await self.client.request(method, url, **kwargs)

        # 응답 처리
        if response.status_code == 200:
            return response
        else:
            logger.error(f"11번가 API 오류: {response.status_code} - {response.text}")
            raise Exception(f"API 오류: {response.status_code}")

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
