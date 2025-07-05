"""
상품 데이터 모델 정의
모든 공급사/마켓플레이스 간 데이터 교환을 위한 표준 형식
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProductStatus(str, Enum):
    """상품 상태"""

    ACTIVE = "active"  # 판매중
    INACTIVE = "inactive"  # 판매중지
    OUT_OF_STOCK = "out_of_stock"  # 품절
    DISCONTINUED = "discontinued"  # 단종
    PENDING = "pending"  # 검토중
    ERROR = "error"  # 오류


class OptionType(str, Enum):
    """옵션 타입"""

    SELECT = "select"  # 단일 선택
    MULTI = "multi"  # 다중 선택
    TEXT = "text"  # 텍스트 입력


class ProductOption(BaseModel):
    """상품 옵션"""

    name: str = Field(..., description="옵션명 (예: 색상, 사이즈)")
    type: OptionType = Field(default=OptionType.SELECT)
    values: List[str] = Field(default_factory=list, description="옵션값 목록")
    required: bool = Field(default=True, description="필수 옵션 여부")

    model_config = ConfigDict(use_enum_values=True)


class ProductVariant(BaseModel):
    """상품 변형 (옵션 조합)"""

    sku: str = Field(..., description="변형 고유 코드")
    options: Dict[str, str] = Field(..., description="옵션명: 옵션값 매핑")
    price: Optional[Decimal] = Field(None, description="변형별 가격 (기본 가격과 다른 경우)")
    stock: int = Field(default=0, description="재고 수량")
    status: ProductStatus = Field(default=ProductStatus.ACTIVE)
    barcode: Optional[str] = Field(None, description="바코드")


class ProductImage(BaseModel):
    """상품 이미지"""

    url: HttpUrl = Field(..., description="이미지 URL")
    alt: Optional[str] = Field(None, description="대체 텍스트")
    is_main: bool = Field(default=False, description="대표 이미지 여부")
    order: int = Field(default=0, description="표시 순서")
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = Field(None, description="파일 크기 (bytes)")


class StandardProduct(BaseModel):
    """표준 상품 데이터 모델"""

    # 기본 정보
    id: str = Field(..., description="상품 고유 ID")
    supplier_id: str = Field(..., description="공급사 코드")
    supplier_product_id: str = Field(..., description="공급사 상품 ID")

    # 상품 정보
    name: str = Field(..., description="상품명")
    description: Optional[str] = Field(None, description="상품 설명")
    brand: Optional[str] = Field(None, description="브랜드")
    manufacturer: Optional[str] = Field(None, description="제조사")
    origin: Optional[str] = Field(None, description="원산지")

    # 카테고리
    category_code: Optional[str] = Field(None, description="공급사 카테고리 코드")
    category_name: Optional[str] = Field(None, description="공급사 카테고리명")
    category_path: Optional[List[str]] = Field(None, description="카테고리 경로")

    # 가격 정보
    cost: Decimal = Field(..., description="원가/공급가")
    price: Decimal = Field(..., description="판매가")
    list_price: Optional[Decimal] = Field(None, description="정가/소비자가")

    # 재고 및 상태
    stock: int = Field(default=0, description="재고 수량")
    status: ProductStatus = Field(default=ProductStatus.ACTIVE)

    # 이미지
    images: List[ProductImage] = Field(default_factory=list)

    # 옵션 및 변형
    options: List[ProductOption] = Field(default_factory=list)
    variants: List[ProductVariant] = Field(default_factory=list)

    # 배송 정보
    shipping_fee: Optional[Decimal] = Field(None, description="배송비")
    is_free_shipping: bool = Field(default=False, description="무료배송 여부")
    shipping_method: Optional[str] = Field(None, description="배송 방법")

    # 추가 속성
    attributes: Dict[str, Any] = Field(default_factory=dict, description="추가 속성")
    tags: List[str] = Field(default_factory=list, description="검색 태그")

    # 메타 정보
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    raw_data: Optional[Dict[str, Any]] = Field(None, description="원본 데이터")

    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
            HttpUrl: lambda v: str(v),
        },
    )

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("가격은 0보다 커야 합니다")
        return v

    @field_validator("cost")
    @classmethod
    def cost_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("원가는 0보다 커야 합니다")
        return v

    @field_validator("images")
    @classmethod
    def ensure_main_image(cls, v):
        """최소 하나의 대표 이미지 보장"""
        if v and not any(img.is_main for img in v):
            v[0].is_main = True
        return v

    @property
    def main_image(self) -> Optional[ProductImage]:
        """대표 이미지 반환"""
        for img in self.images:
            if img.is_main:
                return img
        return self.images[0] if self.images else None

    @property
    def margin(self) -> Decimal:
        """마진 계산"""
        return self.price - self.cost

    @property
    def margin_rate(self) -> Decimal:
        """마진율 계산"""
        if self.price == 0:
            return Decimal(0)
        return (self.margin / self.price) * 100

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return self.model_dump(exclude_none=True)

    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_raw(cls, supplier_id: str, raw_data: Dict[str, Any]) -> StandardProduct:
        """원본 데이터로부터 생성 (하위 클래스에서 구현)"""
        raise NotImplementedError("각 공급사별 파서에서 구현 필요")
