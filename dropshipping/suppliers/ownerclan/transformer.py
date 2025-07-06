"""
오너클랜 상품 변환기
파싱된 데이터를 표준 상품 모델로 변환
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from decimal import Decimal
from dropshipping.models.product import (
    StandardProduct, 
    ProductImage, 
    ProductOption,
    ProductVariant,
    ShippingInfo,
    ProductStatus
)
from dropshipping.transformers.base import BaseTransformer
from dropshipping.monitoring.logger import get_logger

logger = get_logger(__name__)


class OwnerclanTransformer(BaseTransformer):
    """오너클랜 상품 변환기"""
    
    def __init__(self):
        self.supplier_id = "ownerclan"
        self._errors = []

    def to_standard(self, raw_product: Dict[str, Any]) -> Optional[StandardProduct]:
        """원본 상품을 표준 형식으로 변환
        
        Args:
            raw_product: 파싱된 오너클랜 상품 데이터
            
        Returns:
            표준 상품 모델 또는 None
        """
        try:
            # 필수 필드 검증
            if not raw_product.get("id") or not raw_product.get("name"):
                logger.warning(f"필수 필드 누락: {raw_product.get('id')}")
                return None
            
            # 상품 상태 확인 (AVAILABLE, OUT_OF_STOCK 등)
            status = raw_product.get("status", "").upper()
            is_active = status == "AVAILABLE"
            
            # 가격 정보 처리
            original_price = float(raw_product.get("price", 0))
            fixed_price = float(raw_product.get("fixed_price", 0))
            
            # 고정가가 있으면 고정가 사용, 없으면 원가 사용
            base_price = fixed_price if fixed_price > 0 else original_price
            
            # 판매가 계산 (마진 30% 적용)
            selling_price = self._calculate_selling_price(base_price)
            
            # 이미지 처리
            images = self._process_images(raw_product.get("images", []))
            
            # 옵션 처리
            options, variants = self._process_options(raw_product.get("options", []))
            
            # 배송 정보
            shipping_info = self._create_shipping_info(raw_product)
            
            # 재고 수량 (옵션별 재고 또는 기본 재고)
            stock_quantity = raw_product.get("stock", 0)
            if not stock_quantity and variants:
                stock_quantity = sum(v.stock_quantity for v in variants)
            
            # 상품 설명 생성
            description = self._create_description(raw_product)
            
            # 표준 상품 생성
            return StandardProduct(
                id=f"ownerclan_{raw_product['id']}",
                supplier_id="ownerclan",
                supplier_product_id=raw_product["id"],
                name=self._clean_product_name(raw_product["name"]),
                description=description,
                brand=raw_product.get("brand", ""),
                manufacturer=raw_product.get("brand", ""),
                origin=raw_product.get("origin", ""),
                category_code=raw_product.get("category", ""),
                category_name=raw_product.get("category", ""),
                cost=Decimal(str(original_price)),
                price=Decimal(str(selling_price)),
                list_price=Decimal(str(fixed_price)) if fixed_price > 0 else None,
                stock=stock_quantity,
                status=ProductStatus.ACTIVE if is_active else ProductStatus.INACTIVE,
                images=images,
                options=options,
                variants=variants,
                shipping_fee=Decimal(str(shipping_info.fee)),
                is_free_shipping=(shipping_info.method == "무료배송"),
                shipping_method=shipping_info.method,
                attributes={
                    "model": raw_product.get("model", ""),
                    "tax_free": raw_product.get("tax_free", False),
                    "adult_only": raw_product.get("adult_only", False),
                    "returnable": raw_product.get("returnable", True),
                    "shipping_type": raw_product.get("shipping_type", ""),
                    "shipping_info": shipping_info.model_dump(),
                },
                tags=[],
                raw_data=raw_product
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
                if not url.startswith(('http://', 'https://')):
                    url = f"https://ownerclan.com{url}"
                    
                product_images.append(ProductImage(
                    url=url,
                    is_main=(idx == 0),  # 첫 번째 이미지를 메인으로
                    order=idx
                ))
                
        return product_images
    
    def _process_options(self, options: List[Dict[str, Any]]) -> tuple[List[ProductOption], List[ProductVariant]]:
        """옵션 정보를 표준 형식으로 변환
        
        Args:
            options: 파싱된 옵션 목록
            
        Returns:
            (ProductOption 목록, ProductVariant 목록) 튜플
        """
        # 옵션 속성별로 그룹화
        option_groups = {}
        variants = []
        
        for opt in options:
            attributes = opt.get("attributes", {})
            
            # 옵션 속성 수집
            for attr_name, attr_value in attributes.items():
                if attr_name not in option_groups:
                    option_groups[attr_name] = set()
                option_groups[attr_name].add(attr_value)
            
            # 변형 상품 생성
            if opt.get("name"):
                variants.append(ProductVariant(
                    sku=f"OC-{len(variants)+1}",
                    name=opt["name"],
                    stock=int(opt.get("quantity", 0)),
                    attributes=attributes
                ))
        
        # ProductOption 객체 생성
        product_options = []
        for opt_name, opt_values in option_groups.items():
            product_options.append(ProductOption(
                name=opt_name,
                values=list(opt_values),
                required=True
            ))
            
        return product_options, variants
    
    def _create_shipping_info(self, raw_product: Dict[str, Any]) -> ShippingInfo:
        """배송 정보 생성
        
        Args:
            raw_product: 원본 상품 데이터
            
        Returns:
            배송 정보 객체
        """
        shipping_fee = float(raw_product.get("shipping_fee", 0))
        shipping_type = raw_product.get("shipping_type", "")
        
        # 배송 방법 결정
        if shipping_fee == 0 or shipping_type.lower() == "free":
            method = "무료배송"
        elif shipping_type.lower() == "conditional":
            method = "조건부 무료배송"
        else:
            method = "유료배송"
            
        return ShippingInfo(
            method=method,
            fee=shipping_fee,
            estimated_days_min=2,
            estimated_days_max=3,
            free_shipping_minimum=50000 if method == "조건부 무료배송" else None
        )
    
    def _create_description(self, raw_product: Dict[str, Any]) -> str:
        """상품 설명 생성
        
        Args:
            raw_product: 원본 상품 데이터
            
        Returns:
            생성된 설명
        """
        parts = []
        
        # 기본 정보
        if raw_product.get("model"):
            parts.append(f"모델명: {raw_product['model']}")
        
        if raw_product.get("brand"):
            parts.append(f"제조사: {raw_product['brand']}")
            
        if raw_product.get("origin"):
            parts.append(f"원산지: {raw_product['origin']}")
            
        # 특수 정보
        if raw_product.get("tax_free"):
            parts.append("※ 면세 상품입니다.")
            
        if raw_product.get("adult_only"):
            parts.append("※ 성인 인증이 필요한 상품입니다.")
            
        if not raw_product.get("returnable", True):
            parts.append("※ 반품 불가 상품입니다.")
            
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