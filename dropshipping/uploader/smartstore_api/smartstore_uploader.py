"""
네이버 스마트스토어 API 업로더
Commerce API를 통한 상품 업로드
"""

from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from dropshipping.models.product import StandardProduct
from dropshipping.uploader.base import BaseUploader, MarketplaceType


class SmartstoreUploader(BaseUploader):
    """네이버 스마트스토어 업로더"""

    def __init__(self, storage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 스마트스토어 API 설정
                - client_id: 애플리케이션 ID
                - client_secret: 애플리케이션 시크릿
                - access_token: 액세스 토큰
                - channel_id: 채널 ID
        """
        super().__init__(MarketplaceType.NAVER, storage, config)

        # API 설정
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.access_token = self.config.get("access_token")
        self.channel_id = self.config.get("channel_id")

        # API 엔드포인트
        self.base_url = "https://api.commerce.naver.com/external"

        # 네이버 카테고리 매핑
        self.category_mapping = {
            "전자기기/이어폰": "50000190",  # 디지털/가전 > 이어폰/헤드폰
            "의류/여성의류": "50000167",  # 패션의류 > 여성의류
            "애완용품": "50000197",  # 생활/건강 > 반려동물용품
            # 실제로는 더 많은 매핑 필요
        }

        # HTTP 클라이언트
        self.client = httpx.AsyncClient(timeout=30.0)

    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        """상품 검증"""
        errors = []

        # 필수 필드 검증
        if not product.name:
            errors.append("상품명 누락")
        elif len(product.name) < 10:
            errors.append("상품명이 너무 짧습니다 (최소 10자)")
        elif len(product.name) > 100:
            errors.append("상품명이 너무 깁니다 (최대 100자)")

        if not product.price or product.price < 100:
            errors.append("판매가격이 너무 낮습니다 (최소 100원)")
        elif product.price > 999999999:
            errors.append("판매가격이 너무 높습니다")

        if not product.images or len(product.images) == 0:
            errors.append("대표 이미지가 없습니다")

        # 카테고리 확인
        if product.category_name not in self.category_mapping:
            errors.append(f"지원하지 않는 카테고리: {product.category_name}")

        # 재고 확인
        if product.stock < 0:
            errors.append("재고수량이 음수입니다")

        if errors:
            return False, "; ".join(errors)

        return True, None

    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """상품 데이터 변환"""

        # 스마트스토어 형식으로 변환
        smartstore_data = {
            "originProduct": {
                "statusType": "SALE",  # 판매중
                "saleType": "NEW",  # 신상품
                "leafCategoryId": self.category_mapping.get(product.category_name),
                "name": product.name[:100],
                "detailContent": self._create_detail_content(product),
                "images": {
                    "representativeImage": {"url": str(product.images[0].url)},
                    "optionalImages": [
                        {"url": str(img.url)} for img in product.images[1:10]  # 최대 10개
                    ],
                },
                "salePrice": int(product.price),
                "stockQuantity": product.stock,
                "deliveryInfo": {
                    "deliveryType": "DELIVERY",  # 택배배송
                    "deliveryAttributeType": "NORMAL",  # 일반배송
                    "deliveryCompany": "CJGLS",  # CJ대한통운
                    "outboundLocationId": self.config.get("outbound_location_id", ""),
                    "deliveryFee": {
                        "deliveryFeeType": "CONDITIONAL_FREE",  # 조건부 무료
                        "baseFee": 2500,
                        "freeConditionalAmount": 30000,  # 3만원 이상 무료
                    },
                    "claimDeliveryInfo": {
                        "returnDeliveryCompanyPriorityType": "PRIMARY",
                        "returnDeliveryFee": 2500,
                        "exchangeDeliveryFee": 5000,
                        "shippingAddress": {
                            "addressType": "ROADNAME",
                            "baseAddress": self.config.get("return_address", ""),
                            "detailAddress": self.config.get("return_detail_address", ""),
                            "zipCode": self.config.get("return_zip_code", ""),
                            "tel1": self.config.get("return_tel", ""),
                        },
                    },
                },
                "productInfoProvidedNotice": self._create_product_notice(product),
                "productAttributes": [
                    {
                        "attributeSeq": 1,
                        "attributeValueSeq": 1,
                        "attributeRealValue": product.brand or "기타",
                        "attributeRealValueUnitCode": "",
                    }
                ],
                "certificationTargetExcludeContent": {
                    "childCertifiedProductExclusionYn": "KC_EXEMPTION",
                    "greenCertifiedProductExclusionYn": "GREEN_EXEMPTION",
                    "kcCertifiedProductExclusionYn": "KC_EXEMPTION",
                    "kcExemptionType": "OVERSEAS",
                },
                "sellerManagementCode": product.id,
                "barcode": product.barcode,
                "externalVendorSku": product.supplier_product_id,
                "singleItemYn": "Y" if not product.variants else "N",
            }
        }

        # 옵션 정보 추가
        if product.variants:
            smartstore_data["originProduct"]["optionInfo"] = self._create_options(product)

        return smartstore_data

    def _create_detail_content(self, product: StandardProduct) -> str:
        """상세 컨텐츠 생성"""
        content = f"""
        <div style="font-family: 'Noto Sans KR', sans-serif; line-height: 1.8; padding: 20px;">
            <h1 style="color: #333; border-bottom: 2px solid #03C75A; padding-bottom: 10px;">
                {product.name}
            </h1>
            
            <div style="margin: 20px 0;">
                {product.description or '<p>고품질의 상품을 합리적인 가격에 제공합니다.</p>'}
            </div>
            
            <h2 style="color: #333; margin-top: 30px;">상품 특징</h2>
            <ul style="line-height: 2;">
                <li>정품 보증</li>
                <li>빠른 배송</li>
                <li>안전한 포장</li>
                <li>A/S 가능</li>
            </ul>
            
            <h2 style="color: #333; margin-top: 30px;">배송 안내</h2>
            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px; background: #f5f5f5;">배송비</td>
                    <td style="border: 1px solid #ddd; padding: 10px;">2,500원 (3만원 이상 무료)</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px; background: #f5f5f5;">배송기간</td>
                    <td style="border: 1px solid #ddd; padding: 10px;">평균 2-3일</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px; background: #f5f5f5;">택배사</td>
                    <td style="border: 1px solid #ddd; padding: 10px;">CJ대한통운</td>
                </tr>
            </table>
            
            <div style="margin-top: 30px; padding: 20px; background: #f8f8f8; border-radius: 5px;">
                <strong>교환/반품 안내</strong>
                <p>상품 수령 후 7일 이내 교환/반품이 가능합니다.</p>
                <p>단순 변심의 경우 왕복 배송비는 구매자 부담입니다.</p>
            </div>
        </div>
        """
        return content

    def _create_product_notice(self, product: StandardProduct) -> Dict[str, Any]:
        """상품정보제공고시 생성"""
        # 카테고리별로 다른 고시 정보가 필요하지만, 여기서는 기본값 사용
        return {
            "productInfoProvidedNoticeType": "ETC",  # 기타
            "productInfoProvidedNoticeContent": {
                "품명": product.name[:50],
                "모델명": product.attributes.get("model", "상세페이지 참조"),
                "제조자": product.attributes.get("manufacturer", "상세페이지 참조"),
                "제조국": "상세페이지 참조",
                "품질보증기준": "제품 이상 시 공정거래위원회 고시 소비자분쟁해결기준에 의거 보상합니다.",
                "A/S 책임자와 전화번호": self.config.get("as_contact", "고객센터 1577-0000"),
            },
        }

    def _create_options(self, product: StandardProduct) -> Dict[str, Any]:
        """옵션 정보 생성"""
        option_info = {"optionUsable": True, "options": []}

        # 옵션 그룹 생성 (단일 그룹으로 처리)
        option_values = []
        for i, variant in enumerate(product.variants):
            option_values.append(
                {
                    "value": variant.option_value,
                    "optionPrice": 0,  # 옵션 추가금 없음
                    "stockQuantity": variant.stock,
                    "sellerManagementCode": f"{product.id}-{variant.option_value}",
                    "usable": True,
                }
            )

        option_info["options"].append(
            {"groupName": variant.name if product.variants else "옵션", "values": option_values}
        )

        return option_info

    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """단일 상품 업로드"""
        try:
            # API 호출
            response = await self._api_request("POST", "/v2/products", json=product_data)

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "product_id": result.get("id"),
                    "message": "상품 등록 성공",
                }
            else:
                error_data = response.json()
                return {
                    "success": False,
                    "error": error_data.get("message", "업로드 실패"),
                    "code": error_data.get("code"),
                    "details": error_data.get("invalidInputs", []),
                }

        except Exception as e:
            logger.error(f"스마트스토어 업로드 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    async def update_single(
        self, marketplace_product_id: str, product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """단일 상품 수정"""
        try:
            # API 호출
            response = await self._api_request(
                "PUT", f"/v2/products/{marketplace_product_id}", json=product_data
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "product_id": marketplace_product_id,
                    "message": "상품 수정 성공",
                }
            else:
                error_data = response.json()
                return {
                    "success": False,
                    "error": error_data.get("message", "수정 실패"),
                    "code": error_data.get("code"),
                    "details": error_data.get("invalidInputs", []),
                }

        except Exception as e:
            logger.error(f"스마트스토어 수정 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """상품 상태 확인"""
        try:
            response = await self._api_request("GET", f"/v2/products/{marketplace_product_id}")

            if response.status_code == 200:
                data = response.json()
                origin_product = data.get("originProduct", {})

                return {
                    "success": True,
                    "status": origin_product.get("statusType"),
                    "status_name": self._get_status_name(origin_product.get("statusType", "")),
                    "product_data": data,
                }
            else:
                error_data = response.json()
                return {"success": False, "error": error_data.get("message", "조회 실패")}

        except Exception as e:
            logger.error(f"스마트스토어 상태 확인 오류: {str(e)}")
            return {"success": False, "error": str(e)}

    def _get_status_name(self, status_type: str) -> str:
        """상태 타입을 이름으로 변환"""
        status_mapping = {
            "SALE": "판매중",
            "OUTOFSTOCK": "품절",
            "PROHIBITION": "판매금지",
            "SUSPENSION": "판매중지",
            "CLOSE": "판매종료",
            "DELETE": "삭제",
        }
        return status_mapping.get(status_type, "알 수 없음")

    async def _api_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """스마트스토어 API 요청"""

        # 인증 헤더
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        headers["Content-Type"] = "application/json"
        kwargs["headers"] = headers

        # 요청 URL
        url = self.base_url + path

        # API 호출
        logger.debug(f"스마트스토어 API 호출: {method} {url}")

        response = await self.client.request(method, url, **kwargs)

        return response

    async def refresh_token(self) -> bool:
        """액세스 토큰 갱신"""
        try:
            # OAuth 2.0 토큰 갱신
            token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"

            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.config.get("refresh_token"),
            }

            response = await self.client.post(token_url, data=data)

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                self.config["access_token"] = self.access_token

                # 새 refresh_token이 있으면 업데이트
                if "refresh_token" in token_data:
                    self.config["refresh_token"] = token_data["refresh_token"]

                logger.info("스마트스토어 토큰 갱신 성공")
                return True
            else:
                logger.error(f"토큰 갱신 실패: {response.text}")
                return False

        except Exception as e:
            logger.error(f"토큰 갱신 오류: {str(e)}")
            return False

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
