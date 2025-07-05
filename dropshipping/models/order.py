"""
주문 관련 데이터 모델
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderStatus(str, Enum):
    """주문 상태"""

    PENDING = "pending"  # 주문 접수
    CONFIRMED = "confirmed"  # 주문 확인
    PREPARING = "preparing"  # 상품 준비중
    SHIPPED = "shipped"  # 배송중
    DELIVERED = "delivered"  # 배송완료
    CANCELLED = "cancelled"  # 취소
    REFUNDED = "refunded"  # 환불
    EXCHANGED = "exchanged"  # 교환


class PaymentStatus(str, Enum):
    """결제 상태"""

    PENDING = "pending"  # 결제 대기
    COMPLETED = "completed"  # 결제 완료
    FAILED = "failed"  # 결제 실패
    CANCELLED = "cancelled"  # 결제 취소
    REFUNDED = "refunded"  # 환불 완료
    PARTIAL_REFUNDED = "partial_refunded"  # 부분 환불


class DeliveryStatus(str, Enum):
    """배송 상태"""

    PENDING = "pending"  # 배송 대기
    PREPARING = "preparing"  # 배송 준비중
    IN_TRANSIT = "in_transit"  # 배송중
    OUT_FOR_DELIVERY = "out_for_delivery"  # 배송출발
    DELIVERED = "delivered"  # 배송완료
    FAILED = "failed"  # 배송실패
    RETURNED = "returned"  # 반송


class PaymentMethod(str, Enum):
    """결제 방법"""

    CARD = "card"  # 신용카드
    BANK = "bank"  # 계좌이체
    VIRTUAL_ACCOUNT = "virtual_account"  # 가상계좌
    PHONE = "phone"  # 휴대폰결제
    CASH = "cash"  # 현금
    POINT = "point"  # 포인트
    PAYPAL = "paypal"  # 페이팔
    OTHER = "other"  # 기타


class OrderItem(BaseModel):
    """주문 상품 항목"""

    # 식별자
    id: str = Field(..., description="주문 항목 ID")

    # 상품 정보
    product_id: str = Field(..., description="우리 시스템 상품 ID")
    marketplace_product_id: str = Field(..., description="마켓플레이스 상품 ID")
    supplier_product_id: str = Field(..., description="공급사 상품 ID")
    product_name: str = Field(..., description="상품명")

    # 옵션 정보
    variant_id: Optional[str] = Field(None, description="변형 상품 ID")
    options: Dict[str, str] = Field(default_factory=dict, description="옵션 정보")

    # 수량 및 가격
    quantity: int = Field(..., gt=0, description="주문 수량")
    unit_price: Decimal = Field(..., description="단가")
    total_price: Decimal = Field(..., description="총 가격")

    # 할인 정보
    discount_amount: Decimal = Field(default=Decimal("0"), description="할인 금액")
    coupon_discount: Decimal = Field(default=Decimal("0"), description="쿠폰 할인")

    # 상태
    status: OrderStatus = Field(default=OrderStatus.PENDING)

    @field_validator("total_price")
    @classmethod
    def validate_total_price(cls, v, info):
        """총 가격 검증"""
        if "unit_price" in info.data and "quantity" in info.data:
            expected = info.data["unit_price"] * info.data["quantity"]
            if abs(v - expected) > Decimal("0.01"):  # 1원 오차 허용
                raise ValueError(f"총 가격이 맞지 않습니다. 예상: {expected}, 실제: {v}")
        return v


class CustomerInfo(BaseModel):
    """고객 정보"""

    name: str = Field(..., description="고객명")
    phone: str = Field(..., description="연락처")
    email: Optional[str] = Field(None, description="이메일")

    # 배송 정보
    recipient_name: str = Field(..., description="수령인명")
    recipient_phone: str = Field(..., description="수령인 연락처")
    postal_code: str = Field(..., description="우편번호")
    address: str = Field(..., description="주소")
    address_detail: Optional[str] = Field(None, description="상세주소")
    delivery_message: Optional[str] = Field(None, description="배송 메시지")

    # 마켓플레이스 정보
    marketplace_customer_id: Optional[str] = Field(None, description="마켓플레이스 고객 ID")


class PaymentInfo(BaseModel):
    """결제 정보"""

    method: PaymentMethod = Field(..., description="결제 방법")
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)

    # 금액 정보
    total_amount: Decimal = Field(..., description="총 결제 금액")
    product_amount: Decimal = Field(..., description="상품 금액")
    shipping_fee: Decimal = Field(default=Decimal("0"), description="배송비")
    discount_amount: Decimal = Field(default=Decimal("0"), description="할인 금액")

    # 결제 상세
    transaction_id: Optional[str] = Field(None, description="거래 ID")
    paid_at: Optional[datetime] = Field(None, description="결제 시간")

    # 환불 정보
    refund_amount: Decimal = Field(default=Decimal("0"), description="환불 금액")
    refunded_at: Optional[datetime] = Field(None, description="환불 시간")


class DeliveryInfo(BaseModel):
    """배송 정보"""

    method: str = Field(default="택배", description="배송 방법")
    status: DeliveryStatus = Field(default=DeliveryStatus.PENDING)
    carrier: Optional[str] = Field(None, description="택배사")
    tracking_number: Optional[str] = Field(None, description="운송장번호")

    # 배송 일정
    requested_date: Optional[datetime] = Field(None, description="요청배송일")
    shipped_at: Optional[datetime] = Field(None, description="발송일시")
    delivered_at: Optional[datetime] = Field(None, description="배송완료일시")
    estimated_delivery: Optional[datetime] = Field(None, description="예상배송일")

    # 배송 추적
    tracking_url: Optional[str] = Field(None, description="배송조회 URL")
    tracking_history: List[Dict[str, Any]] = Field(default_factory=list)


class Order(BaseModel):
    """주문 정보"""

    model_config = ConfigDict(use_enum_values=True)

    # 주문 식별자
    id: str = Field(..., description="주문 ID")
    marketplace: str = Field(..., description="마켓플레이스 (coupang, 11st, etc)")
    marketplace_order_id: str = Field(..., description="마켓플레이스 주문번호")

    # 주문 정보
    order_date: datetime = Field(..., description="주문일시")
    status: OrderStatus = Field(default=OrderStatus.PENDING)

    # 상품 정보
    items: List[OrderItem] = Field(..., min_length=1, description="주문 상품 목록")

    # 고객 정보
    customer: CustomerInfo = Field(..., description="고객 정보")

    # 결제 정보
    payment: PaymentInfo = Field(..., description="결제 정보")

    # 배송 정보
    delivery: DeliveryInfo = Field(..., description="배송 정보")

    # 공급사 주문 정보
    supplier_order_id: Optional[str] = Field(None, description="공급사 주문번호")
    supplier_order_status: Optional[str] = Field(None, description="공급사 주문상태")
    supplier_ordered_at: Optional[datetime] = Field(None, description="공급사 주문일시")

    # 메타 정보
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    raw_data: Optional[Dict[str, Any]] = Field(None, description="원본 주문 데이터")

    @property
    def total_amount(self) -> Decimal:
        """총 주문 금액"""
        return sum(item.total_price for item in self.items)

    @property
    def total_quantity(self) -> int:
        """총 주문 수량"""
        return sum(item.quantity for item in self.items)

    @property
    def is_completed(self) -> bool:
        """주문 완료 여부"""
        return self.status == OrderStatus.DELIVERED

    @property
    def is_cancellable(self) -> bool:
        """취소 가능 여부"""
        return self.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return self.model_dump(exclude_none=True)


class OrderUpdate(BaseModel):
    """주문 업데이트 정보"""

    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    delivery_status: Optional[DeliveryStatus] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    supplier_order_id: Optional[str] = None
    supplier_order_status: Optional[str] = None
    notes: Optional[str] = None
