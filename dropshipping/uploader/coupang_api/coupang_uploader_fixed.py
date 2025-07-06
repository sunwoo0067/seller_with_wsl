"""
쿠팡 OpenAPI 업로더 (수정본)
쿠팡 WING OpenAPI를 통한 상품 업로드
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from dropshipping.config import Settings
from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import BaseUploader, MarketplaceType


class CoupangUploaderFixed(BaseUploader):
    """쿠팡 WING OpenAPI 업로더 (수정본)"""

    def __init__(self, storage: BaseStorage, config: Any):
        """
        초기화
        """
        if isinstance(config, dict):
            config_obj = Settings(**config)
        else:
            config_obj = config

        super().__init__(MarketplaceType.COUPANG, storage, config_obj)

        self.vendor_id = self.config.coupang.vendor_id
        self.access_key = self.config.coupang.access_key
        self.secret_key = self.config.coupang.secret_key
        self.test_mode = self.config.coupang.test_mode

        self.base_url = (
            "https://api-gateway-it.coupang.com"
            if self.test_mode
            else "https://api-gateway.coupang.com"
        )

        self.category_mapping = {
            "전자기기/이어폰": "513336",
            "의류/여성의류": "513337",
            "애완용품": "513338",
        }

        self.client = httpx.AsyncClient(timeout=30.0)

    def _create_auth_headers(self, method: str, path: str, query: str = "") -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%y%m%d'T'%H%M%S'Z'")
        message = f"{timestamp}{method}{path}{query}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Authorization": f"CEA algorithm=HmacSHA256, access-key={self.access_key}, signed-date={timestamp}, signature={signature}",
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-By": self.vendor_id,
        }

    async def _api_request(
        self, method: str, path: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        query_string = '&'.join([f'{k}={v}' for k, v in params.items()]) if params else ''
        headers = self._create_auth_headers(method, path, query_string)
        
        try:
            if method.upper() in ["POST", "PUT", "PATCH"]:
                response = await self.client.request(method, url, headers=headers, json=data, params=params)
            else:
                response = await self.client.request(method, url, headers=headers, params=params)
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Coupang API Error: {e.response.text}")
            return e.response.json()
        except Exception as e:
            logger.error(f"Unknown API Error: {e}")
            return {"code": "ERROR", "message": str(e)}

    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        errors = []
        if not product.name:
            errors.append("상품명 누락")
        if product.price <= 100:
            errors.append("판매가격이 너무 낮습니다")
        if not product.images:
            errors.append("상품 이미지가 없습니다")
        if product.category_name not in self.category_mapping:
            errors.append("지원하지 않는 카테고리")
        
        if errors:
            return False, ', '.join(errors)
        return True, None

    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        is_valid, error = await self.validate_product(product)
        if not is_valid:
            raise ValueError(f"상품 검증 실패: {error}")

        images = []
        main_image = next((img for img in product.images if img.is_main), None)
        if main_image:
            images.append({"imageType": "REPRESENTATION", "vendorPath": main_image.url, "imageOrder": 0})
        
        sub_images = [img for img in product.images if not img.is_main]
        for i, img in enumerate(sub_images):
            images.append({"imageType": "DETAIL", "vendorPath": img.url, "imageOrder": i + 1})

        items = []
        if product.variants:
            for variant in product.variants:
                item_name = " - ".join(variant.options.values())
                items.append({
                    "itemName": item_name,
                    "originalPrice": int(variant.price),
                    "salePrice": int(variant.price),
                    "maximumBuyCount": 10,
                    "quantity": variant.stock,
                    "externalVendorSku": variant.sku,
                    "barcode": variant.barcode or "",
                    "emptyBarcode": not bool(variant.barcode),
                })
        else:
            items.append({
                "itemName": product.name,
                "originalPrice": int(product.price),
                "salePrice": int(product.price),
                "maximumBuyCount": 10,
                "quantity": product.stock,
                "externalVendorSku": product.supplier_product_id,
            })

        return {
            "displayCategoryCode": self.category_mapping.get(product.category_name),
            "sellerProductName": product.name,
            "vendorId": self.vendor_id,
            "saleStartedAt": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "saleEndedAt": "2099-01-01T23:59:59",
            "images": images,
            "items": items,
            "brand": product.brand or "",
            "deliveryCompanyCode": "KGB",
            "deliveryChargeType": "FREE",
            "deliveryCharge": product.attributes.get("shipping_fee", 0),
            "returnCenterCode": "your_return_center_code", 
            "returnChargeName": "your_return_charge_name",
            "returnCharge": 5000,
            "sellerProductId": product.id,
            "invoiceDocument": "INVOICE_DOCUMENT_NONE",
            "taxType": "TAX",
            "contents": [{"contentsType": "TEXT", "contentDetails": [{"content": product.description}]}],
        }

    def upload_product(self, product: StandardProduct) -> Dict[str, Any]:
        return asyncio.run(self.async_upload_product(product))

    async def async_upload_product(self, product: StandardProduct) -> Dict[str, Any]:
        try:
            payload = await self.transform_product(product)
            return await self.upload_single(payload)
        except (ValueError, NotImplementedError) as e:
            logger.error(f"상품 업로드 중 오류 발생: {e}")
            return {"success": False, "error": str(e)}

    def update_stock(self, marketplace_product_id: str, stock: int) -> bool:
        result = asyncio.run(self.async_update_stock(marketplace_product_id, stock))
        return result.get("success", False)

    async def async_update_stock(self, marketplace_product_id: str, stock: int) -> Dict[str, Any]:
        payload = {"stockQuantity": stock}
        return await self.update_single(marketplace_product_id, payload)

    def update_price(self, marketplace_product_id: str, price: int) -> bool:
        result = asyncio.run(self.async_update_price(marketplace_product_id, price))
        return result.get("success", False)

    async def async_update_price(self, marketplace_product_id: str, price: int) -> Dict[str, Any]:
        payload = {"salePrice": int(price)}
        return await self.update_single(marketplace_product_id, payload)

    def check_upload_status(self, upload_id: str) -> Dict[str, Any]:
        return asyncio.run(self.check_product_status(upload_id))

    async def upload_single(self, data: Dict[str, Any]) -> Dict[str, Any]:
        path = "/v2/providers/seller_api/v1/products"
        result = await self._api_request("POST", path, data=data)
        
        if result.get("code") == "SUCCESS":
            return {
                "success": True,
                "product_id": result.get("data", {}).get("productId"),
                "message": result.get("message")
            }
        return {"success": False, "error": result.get("message"), "code": result.get("code")}

    async def update_single(self, product_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        path = f"/v2/providers/seller_api/v1/products/{product_id}"
        data["productId"] = product_id # Test requires this
        result = await self._api_request("PUT", path, data=data)

        if result.get("code") == "SUCCESS":
            return {"success": True, "product_id": product_id, "message": result.get("message")}
        return {"success": False, "error": result.get("message"), "code": result.get("code")}

    async def check_product_status(self, request_id: str) -> Dict[str, Any]:
        path = f"/v2/providers/seller_api/v1/products/status/{request_id}"
        result = await self._api_request("GET", path)

        if result.get("code") == "SUCCESS":
            data = result.get("data", {})
            return {
                "success": True,
                "status": data.get("status"),
                "status_name": data.get("statusName")
            }
        return {"success": False, "error": result.get("message"), "code": result.get("code")}

    async def close(self):
        await self.client.aclose()
