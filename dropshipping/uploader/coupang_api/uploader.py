"""
쿠팡 API 업로더
"""

import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional, Tuple

import requests
from loguru import logger

from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import BaseUploader, MarketplaceType


class CoupangUploader(BaseUploader):
    """쿠팡 API를 통한 상품 업로드 및 관리"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(MarketplaceType.COUPANG, storage, config)
        self.base_url = "https://api-gateway.coupang.com"
        self.vendor_id = self.config.get("vendor_id")

        if not self.api_key or not self.api_secret or not self.vendor_id:
            raise ValueError("쿠팡 API 키, 시크릿 키, 벤더 ID가 필요합니다.")

    def _generate_signature(self, method: str, url: str) -> Dict[str, str]:
        """
        쿠팡 API 요청을 위한 서명 생성
        참고: https://developers.coupang.com/hc/ko/articles/360033834174
        """
        path = url.replace(self.base_url, "")
        timestamp = str(int(time.time() * 1000))

        message = timestamp + method + path
        if "query_string" in url:
            message += url.split("?")[1]

        # HMAC-SHA256 서명 생성
        signature = hmac.new(
            bytes(self.api_secret, "utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        # Base64 인코딩
        encoded_signature = base64.b64encode(signature).decode("utf-8")

        return {
            "X-Requested-With": "XMLHttpRequest",
            "Authorization": f"CEA algorithm=HMAC-SHA256, access-key={self.api_key}, signed-headers=X-Requested-With;Host;Content-Type, signature={encoded_signature}",
            "X-Timestamp": timestamp,
            "Content-Type": "application/json;charset=UTF-8",
        }

    async def _api_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        쿠팡 API 요청 공통 메서드 (재시도 포함)
        """
        url = f"{self.base_url}{path}"
        headers = self._generate_signature(method, url)

        for attempt in range(self.max_retries):
            try:
                if method == "GET":
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                elif method == "PUT":
                    response = requests.put(url, headers=headers, json=data, timeout=10)
                else:
                    raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

                response.raise_for_status()  # 2xx 이외의 상태 코드에 대해 예외 발생
                return response.json()

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"쿠팡 API 요청 실패 (시도 {attempt + 1}/{self.max_retries}): {str(e)}"
                )
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)
        raise Exception("API 요청 재시도 모두 실패")

    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        """
        쿠팡 상품 등록을 위한 기본 검증
        (더 상세한 검증은 ProductValidator에서 수행)
        """
        if not product.name:
            return False, "상품명이 없습니다."
        if not product.price or product.price <= 0:
            return False, "유효한 판매가가 없습니다."
        if not product.images:
            return False, "이미지가 없습니다."
        if not product.supplier_product_id:
            return False, "공급사 상품 ID가 없습니다."
        return True, None

    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """
        StandardProduct를 쿠팡 상품 등록 형식으로 변환
        (매우 간소화된 버전, 실제로는 훨씬 복잡함)
        """
        # 쿠팡 카테고리 매핑 (예시)
        # 실제로는 CategoryMapper를 통해 DB에서 가져와야 함
        coupang_category_code = "194176"  # 예시: 여성패션
        if product.category_code:
            # TODO: CategoryMapper를 사용하여 실제 매핑 로직 구현
            pass

        # 이미지 변환
        images = []
        for i, img in enumerate(product.images):
            images.append(
                {
                    "vendorPath": img.url,  # 외부 URL 직접 사용 (쿠팡 정책에 따라 다를 수 있음)
                    "displayOrder": i + 1,
                    "imageType": "DETAIL" if not img.is_main else "REPRESENTATIVE",
                }
            )

        # 옵션 변환 (단일 옵션만 가정)
        options = []
        if product.options:
            for opt in product.options:
                for val in opt.values:
                    options.append(
                        {
                            "attributes": [
                                {"attributeTypeName": opt.name, "attributeValueName": val}
                            ],
                            "originalPrice": float(product.list_price or product.price),
                            "salePrice": float(product.price),
                            "stockQuantity": product.stock,
                            "vendorItemCode": f"{product.supplier_product_id}-{opt.name}-{val}",
                            "sellerProductItemName": f"{product.name} - {opt.name}: {val}",
                        }
                    )
        else:
            # 옵션이 없는 경우
            options.append(
                {
                    "originalPrice": float(product.list_price or product.price),
                    "salePrice": float(product.price),
                    "stockQuantity": product.stock,
                    "vendorItemCode": product.supplier_product_id,
                    "sellerProductItemName": product.name,
                }
            )

        # 반품/교환 정보 (기본값)
        return_info = {
            "returnCharge": 2500,
            "exchangeCharge": 5000,
            "returnChargeDeliveryCompanyCode": "CJGLS",
            "returnChargeDeliveryCompany": "CJ대한통운",
            "returnCenterCode": "12345",  # 판매자 반품지 코드
            "returnCenterName": "테스트 반품지",
        }

        # 상품 등록 요청 본문 구성
        return {
            "vendorId": self.vendor_id,
            "sellerProductName": product.name,
            "displayCategoryCode": coupang_category_code,
            "vendorProductCode": product.supplier_product_id,
            "originalPrice": float(product.list_price or product.price),
            "salePrice": float(product.price),
            "stockQuantity": product.stock,
            "deliveryCompanyCode": "CJGLS",
            "deliveryCompany": "CJ대한통운",
            "deliveryChargeType": "FREE",  # 무료배송
            "deliveryCharge": 0,
            "outboundShippingPlaceCode": "12345",  # 판매자 출고지 코드
            "outboundShippingPlaceName": "테스트 출고지",
            "images": images,
            "items": options,
            "productAttributes": [],  # 추가 속성 (필요시 매핑)
            "productCertifications": [],  # 인증 정보 (필요시)
            "productNotices": [],  # 상품 고시 정보 (필요시)
            "returnInfo": return_info,
            "sellerProductDescription": product.description or product.name,  # 설명
            "maximumBuyQuantity": 999,  # 최대 구매 수량
            "minimumBuyQuantity": 1,  # 최소 구매 수량
            "taxType": "TAX",  # 과세 상품
            "externalVendorId": product.supplier_id,  # 외부 공급사 ID
        }

    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        단일 상품 업로드 (신규 등록)
        """
        path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        try:
            response = await self._api_request("POST", path, data=product_data)
            if response.get("code") == "SUCCESS":
                return {"success": True, "product_id": response.get("data", {}).get("productId")}
            else:
                logger.error(f"쿠팡 상품 등록 실패: {response.get("message")}")
                return {"success": False, "error": response.get("message")}
        except Exception as e:
            logger.error(f"쿠팡 상품 등록 중 예외 발생: {str(e)}")
            return {"success": False, "error": str(e)}

    async def update_single(
        self, marketplace_product_id: str, product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        단일 상품 수정 (재고, 가격 등)
        """
        # 쿠팡은 상품 수정 API가 복잡하므로, 여기서는 재고/가격만 예시
        # 실제로는 아이템 단위로 수정해야 함
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{marketplace_product_id}/items"

        # 재고 및 가격 정보만 업데이트하는 예시
        update_data = {
            "vendorId": self.vendor_id,
            "items": product_data["items"],  # items 필드만 사용
        }

        try:
            response = await self._api_request("PUT", path, data=update_data)
            if response.get("code") == "SUCCESS":
                return {"success": True, "product_id": marketplace_product_id}
            else:
                logger.error(f"쿠팡 상품 수정 실패: {response.get("message")}")
                return {"success": False, "error": response.get("message")}
        except Exception as e:
            logger.error(f"쿠팡 상품 수정 중 예외 발생: {str(e)}")
            return {"success": False, "error": str(e)}

    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """
        상품 상태 확인
        """
        path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{marketplace_product_id}"
        try:
            response = await self._api_request("GET", path)
            if response.get("code") == "SUCCESS":
                return {"success": True, "status": response.get("data", {}).get("status")}
            else:
                logger.error(f"쿠팡 상품 상태 조회 실패: {response.get("message")}")
                return {"success": False, "error": response.get("message")}
        except Exception as e:
            logger.error(f"쿠팡 상품 상태 조회 중 예외 발생: {str(e)}")
            return {"success": False, "error": str(e)}
