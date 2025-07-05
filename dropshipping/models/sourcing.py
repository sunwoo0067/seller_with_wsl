"""
소싱 인텔리전스 데이터 모델
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TrendDirection(str, Enum):
    """트렌드 방향"""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class SalesMetrics(BaseModel):
    """판매 지표"""

    # 기본 지표
    total_sales: int = Field(..., description="총 판매량")
    total_revenue: Decimal = Field(..., description="총 매출액")
    average_price: Decimal = Field(..., description="평균 판매가")

    # 성장 지표
    growth_rate: float = Field(..., description="성장률 (%)")
    trend: TrendDirection = Field(..., description="트렌드 방향")

    # 시장 점유율
    market_share: Optional[float] = Field(None, description="시장 점유율 (%)")
    rank: Optional[int] = Field(None, description="순위")

    # 기간
    period_start: datetime = Field(..., description="기간 시작")
    period_end: datetime = Field(..., description="기간 종료")


class CompetitorInfo(BaseModel):
    """경쟁사 정보"""

    # 식별 정보
    competitor_id: str = Field(..., description="경쟁사 ID")
    name: str = Field(..., description="경쟁사명")
    marketplace: str = Field(..., description="마켓플레이스")

    # 판매 정보
    product_count: int = Field(..., description="상품 수")
    average_rating: Optional[float] = Field(None, description="평균 평점")
    review_count: Optional[int] = Field(None, description="리뷰 수")

    # 가격 전략
    min_price: Decimal = Field(..., description="최저가")
    max_price: Decimal = Field(..., description="최고가")
    average_price: Decimal = Field(..., description="평균가")

    # 배송 정보
    shipping_method: Optional[str] = Field(None, description="배송 방법")
    average_delivery_days: Optional[int] = Field(None, description="평균 배송일")

    # 업데이트 정보
    last_updated: datetime = Field(..., description="마지막 업데이트")


class KeywordMetrics(BaseModel):
    """키워드 지표"""

    # 키워드 정보
    keyword: str = Field(..., description="키워드")
    category: Optional[str] = Field(None, description="카테고리")

    # 검색 지표
    search_volume: int = Field(..., description="월간 검색량")
    competition_level: str = Field(..., description="경쟁도 (high/medium/low)")

    # 트렌드
    trend: TrendDirection = Field(..., description="트렌드 방향")
    seasonality: Optional[Dict[str, float]] = Field(None, description="계절성 지수")

    # 연관 키워드
    related_keywords: List[str] = Field(default_factory=list, description="연관 키워드")

    # 상품 지표
    product_count: int = Field(..., description="관련 상품 수")
    average_price: Decimal = Field(..., description="평균 가격")
    conversion_rate: Optional[float] = Field(None, description="전환율 (%)")

    # 분석 일자
    analyzed_at: datetime = Field(..., description="분석 일자")


class ProductOpportunity(BaseModel):
    """상품 기회"""

    model_config = ConfigDict(use_enum_values=True)

    # 기회 정보
    opportunity_id: str = Field(..., description="기회 ID")
    opportunity_score: float = Field(..., description="기회 점수 (0-100)", ge=0, le=100)

    # 상품 정보
    product_name: str = Field(..., description="상품명")
    category: str = Field(..., description="카테고리")
    keywords: List[str] = Field(..., description="주요 키워드")

    # 시장 분석
    market_demand: str = Field(..., description="시장 수요 (high/medium/low)")
    competition_level: str = Field(..., description="경쟁도 (high/medium/low)")
    entry_barrier: str = Field(..., description="진입 장벽 (high/medium/low)")

    # 수익성 분석
    estimated_price: Decimal = Field(..., description="예상 판매가")
    estimated_cost: Decimal = Field(..., description="예상 원가")
    estimated_margin: Decimal = Field(..., description="예상 마진")
    estimated_monthly_sales: int = Field(..., description="예상 월 판매량")

    # 공급사 정보
    supplier_count: int = Field(..., description="공급사 수")
    recommended_suppliers: List[str] = Field(default_factory=list, description="추천 공급사")

    # 리스크
    risks: List[str] = Field(default_factory=list, description="리스크 요인")

    # 생성 정보
    created_at: datetime = Field(..., description="생성일시")
    expires_at: Optional[datetime] = Field(None, description="유효기간")


class MarketTrend(BaseModel):
    """시장 트렌드"""

    # 트렌드 정보
    trend_id: str = Field(..., description="트렌드 ID")
    name: str = Field(..., description="트렌드명")
    category: str = Field(..., description="카테고리")

    # 트렌드 지표
    strength: float = Field(..., description="트렌드 강도 (0-100)")
    direction: TrendDirection = Field(..., description="방향")
    momentum: float = Field(..., description="모멘텀")

    # 키워드
    trending_keywords: List[str] = Field(..., description="트렌딩 키워드")
    emerging_keywords: List[str] = Field(default_factory=list, description="신규 키워드")

    # 상품
    trending_products: List[Dict[str, Any]] = Field(default_factory=list, description="트렌딩 상품")

    # 예측
    forecast_period: int = Field(..., description="예측 기간 (일)")
    forecast_direction: TrendDirection = Field(..., description="예측 방향")
    confidence_level: float = Field(..., description="신뢰도 (%)")

    # 분석 정보
    analyzed_at: datetime = Field(..., description="분석일시")
    data_points: int = Field(..., description="데이터 포인트 수")


class SourcingReport(BaseModel):
    """소싱 리포트"""

    # 리포트 정보
    report_id: str = Field(..., description="리포트 ID")
    report_type: str = Field(..., description="리포트 타입")
    title: str = Field(..., description="제목")

    # 기간
    period_start: datetime = Field(..., description="기간 시작")
    period_end: datetime = Field(..., description="기간 종료")

    # 요약
    summary: str = Field(..., description="요약")
    key_findings: List[str] = Field(..., description="주요 발견사항")
    recommendations: List[str] = Field(..., description="추천사항")

    # 상세 데이터
    sales_metrics: Optional[SalesMetrics] = Field(None, description="판매 지표")
    market_trends: List[MarketTrend] = Field(default_factory=list, description="시장 트렌드")
    opportunities: List[ProductOpportunity] = Field(default_factory=list, description="상품 기회")
    competitors: List[Dict[str, Any]] = Field(default_factory=list, description="경쟁사 정보")
    keywords: List[Dict[str, Any]] = Field(default_factory=list, description="키워드 분석")

    # 생성 정보
    created_at: datetime = Field(..., description="생성일시")
    created_by: Optional[str] = Field(None, description="생성자")
