"""
쿠팡 OpenAPI 업로더
쿠팡 WING OpenAPI를 통한 상품 업로드
"""

import json
import hmac
import hashlib
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import httpx

from loguru import logger

from dropshipping.models.product import StandardProduct
from dropshipping.uploader.base import BaseUploader, MarketplaceType, UploadStatus


class CoupangUploader(BaseUploader):
    """쿠팡 업로더"""
    
    def __init__(self, storage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 쿠팡 API 설정
                - api_key: API 액세스 키
                - api_secret: API 시크릿 키
                - vendor_id: 판매자 ID
                - test_mode: 테스트 모드 여부
        """
        super().__init__(MarketplaceType.COUPANG, storage, config)
        
        # API 설정
        self.vendor_id = self.config.get("vendor_id")
        self.test_mode = self.config.get("test_mode", False)
        
        # API 엔드포인트
        if self.test_mode:
            self.base_url = "https://api-gateway-it.coupang.com"
        else:
            self.base_url = "https://api-gateway.coupang.com"
        
        # 쿠팡 카테고리 매핑
        self.category_mapping = {
            "전자기기/이어폰": "1001",
            "의류/여성의류": "1002",
            "애완용품": "1003",
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
        elif len(product.name) > 100:
            errors.append("상품명이 너무 깁니다 (최대 100자)")
        
        if not product.price or product.price < 100:
            errors.append("판매가격이 너무 낮습니다 (최소 100원)")
        
        if not product.images or len(product.images) == 0:
            errors.append("상품 이미지가 없습니다")
        elif len(product.images) > 10:
            errors.append("이미지가 너무 많습니다 (최대 10개)")
        
        # 카테고리 확인
        if product.category_name not in self.category_mapping:
            errors.append(f"지원하지 않는 카테고리: {product.category_name}")
        
        # 배송비 확인
        if not product.attributes:
            product.attributes = {}
        if "shipping_fee" not in product.attributes:
            product.attributes["shipping_fee"] = 2500  # 기본 배송비
        
        if errors:
            return False, "; ".join(errors)
        
        return True, None
    
    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """상품 데이터 변환"""
        
        # 쿠팡 형식으로 변환
        coupang_data = {
            "displayCategoryCode": self.category_mapping.get(product.category_name),
            "sellerProductName": product.name[:100],  # 최대 100자
            "vendorId": self.vendor_id,
            "saleStartedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "saleEndedAt": "2099-12-31 23:59:59",  # 무제한
            "brand": product.brand or "기타",
            "generalProductName": product.name[:30],  # 대표 상품명
            "productGroup": "상품군명",
            "deliveryMethod": "SEQUENCIAL",  # 순차배송
            "deliveryCompanyCode": "KGB",  # 로젠택배
            "deliveryChargeType": "PAY",  # 유료배송
            "deliveryCharge": int(product.attributes.get("shipping_fee", 2500)),
            "freeShipOverAmount": 30000,  # 3만원 이상 무료배송
            "remoteAreaDeliverable": "Y",
            "unionDeliveryType": "UNION_DELIVERY",  # 묶음배송 가능
            "returnCenterCode": self.config.get("return_center_code", "1000274592"),
            "returnChargeName": "대표이름",
            "companyContactNumber": self.config.get("contact_number", "02-1234-5678"),
            "returnZipCode": "12345",
            "returnAddress": "서울특별시 강남구",
            "returnAddressDetail": "역삼동 123-45",
            "afterServiceInformation": "A/S 안내 1577-1234",
            "afterServiceContactNumber": "1577-1234",
            "outboundShippingPlaceCode": self.config.get("shipping_place_code", "74010"),
            
            # 상품 이미지
            "images": [
                {
                    "imageOrder": i,
                    "imageType": "REPRESENTATION" if img.is_main else "DETAIL",
                    "vendorPath": str(img.url)
                }
                for i, img in enumerate(product.images[:10])  # 최대 10개
            ],
            
            # 상품 상세
            "contents": [
                {
                    "contentsType": "HTML",
                    "contentDetails": [
                        {
                            "content": product.description or "<p>상품 상세 설명</p>",
                            "detailType": "TEXT"
                        }
                    ]
                }
            ],
            
            # 옵션 (단품)
            "items": await self._create_items(product),
            
            # 상품고시정보
            "noticeCategories": [
                {
                    "noticeCategoryName": "기타",
                    "noticeCategoryDetailNames": [
                        {
                            "noticeCategoryDetailName": "품명",
                            "content": product.name[:50]
                        },
                        {
                            "noticeCategoryDetailName": "모델명",
                            "content": product.attributes.get("model", "상세페이지참조")
                        }
                    ]
                }
            ],
            
            # 상품 속성
            "attributes": [
                {
                    "attributeTypeName": "수량",
                    "attributeValueName": str(product.stock_quantity)
                }
            ],
            
            # 판매자 상품 코드
            "sellerProductId": product.id,
            "manufacture": product.attributes.get("manufacturer", "제조사")
        }
        
        return coupang_data
    
    async def _create_items(self, product: StandardProduct) -> List[Dict[str, Any]]:
        """옵션(단품) 생성"""
        items = []
        
        if product.variants:
            # 옵션이 있는 경우
            for variant in product.variants:
                item = {
                    "itemName": variant.name,
                    "originalPrice": int(variant.price),
                    "salePrice": int(variant.price * Decimal("0.9")),  # 10% 할인
                    "maximumBuyCount": 10,  # 최대 구매 수량
                    "maximumBuyForPerson": 5,  # 1인당 최대 구매
                    "outboundShippingTimeDay": 2,  # 출고 소요일
                    "maximumBuyForPersonPeriod": 1,  # 1일
                    "unitCount": 1,
                    "adultOnly": "EVERYONE",  # 전연령
                    "taxType": "TAX",  # 과세
                    "parallelImported": "NOT_PARALLEL_IMPORTED",  # 병행수입 아님
                    "overseasPurchased": "NOT_OVERSEAS_PURCHASED",  # 해외구매대행 아님
                    "externalVendorSku": f"{product.id}-{variant.option_value}",
                    "barcode": variant.barcode,
                    "emptyBarcode": not bool(variant.barcode),
                    "emptyBarcodeReason": "상품에 바코드 없음" if not variant.barcode else None,
                    "modelNo": variant.attributes.get("model", ""),
                    "certifications": []  # 인증 정보
                }
                items.append(item)
        else:
            # 단일 상품
            item = {
                "itemName": "단일상품",
                "originalPrice": int(product.price),
                "salePrice": int(product.price * Decimal("0.9")),  # 10% 할인
                "maximumBuyCount": 10,
                "maximumBuyForPerson": 5,
                "outboundShippingTimeDay": 2,
                "maximumBuyForPersonPeriod": 1,
                "unitCount": 1,
                "adultOnly": "EVERYONE",
                "taxType": "TAX",
                "parallelImported": "NOT_PARALLEL_IMPORTED",
                "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
                "externalVendorSku": product.id,
                "barcode": "",
                "emptyBarcode": True,
                "emptyBarcodeReason": "상품에 바코드 없음",
                "modelNo": product.attributes.get("model", ""),
                "certifications": []
            }
            items.append(item)
        
        return items
    
    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """단일 상품 업로드"""
        try:
            # API 호출
            response = await self._api_request(
                "POST",
                "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products",
                json=product_data
            )
            
            if response.get("code") == "SUCCESS":
                return {
                    "success": True,
                    "product_id": response.get("data", {}).get("productId"),
                    "message": response.get("message")
                }
            else:
                return {
                    "success": False,
                    "error": response.get("message", "업로드 실패"),
                    "code": response.get("code")
                }
                
        except Exception as e:
            logger.error(f"쿠팡 업로드 오류: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_single(
        self,
        marketplace_product_id: str,
        product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """단일 상품 수정"""
        try:
            # 상품 ID 추가
            product_data["productId"] = marketplace_product_id
            
            # API 호출
            response = await self._api_request(
                "PUT",
                "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products",
                json=product_data
            )
            
            if response.get("code") == "SUCCESS":
                return {
                    "success": True,
                    "product_id": marketplace_product_id,
                    "message": response.get("message")
                }
            else:
                return {
                    "success": False,
                    "error": response.get("message", "수정 실패"),
                    "code": response.get("code")
                }
                
        except Exception as e:
            logger.error(f"쿠팡 수정 오류: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """상품 상태 확인"""
        try:
            response = await self._api_request(
                "GET",
                f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{marketplace_product_id}"
            )
            
            if response.get("code") == "SUCCESS":
                data = response.get("data", {})
                return {
                    "success": True,
                    "status": data.get("status"),
                    "status_name": data.get("statusName"),
                    "product_data": data
                }
            else:
                return {
                    "success": False,
                    "error": response.get("message", "조회 실패")
                }
                
        except Exception as e:
            logger.error(f"쿠팡 상태 확인 오류: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _api_request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """쿠팡 API 요청"""
        
        # 인증 헤더 생성
        headers = self._create_auth_headers(method, path, kwargs.get("params", {}))
        
        # 요청 URL
        url = self.base_url + path
        
        # API 호출
        logger.debug(f"쿠팡 API 호출: {method} {url}")
        
        response = await self.client.request(
            method,
            url,
            headers=headers,
            **kwargs
        )
        
        # 응답 처리
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"쿠팡 API 오류: {response.status_code} - {response.text}")
            return {
                "code": "ERROR",
                "message": f"API 오류: {response.status_code}"
            }
    
    def _create_auth_headers(
        self,
        method: str,
        path: str,
        params: Dict[str, Any]
    ) -> Dict[str, str]:
        """쿠팡 인증 헤더 생성"""
        
        # 타임스탬프
        timestamp = str(int(time.time() * 1000))
        
        # 메시지 생성
        message = f"{method}{path}{timestamp}"
        
        # 쿼리 파라미터가 있으면 추가
        if params:
            sorted_params = sorted(params.items())
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            message += query_string
        
        # HMAC 서명 생성
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # 헤더 생성
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"CEA algorithm=HmacSHA256, access-key={self.api_key}, signed-date={timestamp}, signature={signature}",
            "X-Requested-By": self.vendor_id
        }
        
        return headers
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()