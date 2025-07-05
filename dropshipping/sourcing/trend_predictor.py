"""
트렌드 예측 시스템
시계열 분석, ML 모델, 시장 신호를 통한 트렌드 예측
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import numpy as np
import statistics
import math

from loguru import logger

from dropshipping.models.sourcing import (
    MarketTrend, TrendDirection, ProductOpportunity
)
from dropshipping.storage.base import BaseStorage
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor


class TrendPredictor:
    """트렌드 예측기"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 예측 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # 예측 설정
        self.prediction_window = self.config.get("prediction_window", 30)  # 예측 기간 (일)
        self.min_confidence = self.config.get("min_confidence", 60.0)  # 최소 신뢰도
        self.signal_weights = self.config.get("signal_weights", {
            "sales": 0.35,
            "keyword": 0.25,
            "competitor": 0.20,
            "seasonality": 0.10,
            "external": 0.10
        })
        
        # 의존성 모듈
        self.sales_analyzer = SalesAnalyzer(storage, config)
        self.keyword_researcher = KeywordResearcher(storage, config)
        self.competitor_monitor = CompetitorMonitor(storage, config)
        
        # 캐시
        self._trend_cache = {}
        self._signal_cache = {}
    
    async def predict_trends(
        self,
        category: Optional[str] = None,
        horizon_days: int = 30
    ) -> List[MarketTrend]:
        """
        트렌드 예측
        
        Args:
            category: 카테고리 (None이면 전체)
            horizon_days: 예측 기간
            
        Returns:
            예측된 트렌드 목록
        """
        try:
            if category:
                categories = [category]
            else:
                categories = await self._get_active_categories()
            
            all_trends = []
            
            for cat in categories:
                # 1. 데이터 수집
                sales_data = await self._collect_sales_data(cat)
                keyword_data = await self._collect_keyword_data(cat)
                competitor_data = await self._collect_competitor_data(cat)
                seasonality_data = await self._analyze_seasonality(cat)
                external_signals = await self._collect_external_signals(cat)
                
                # 2. 신호 분석
                sales_signal = self._analyze_sales_signal(sales_data)
                keyword_signal = self._analyze_keyword_signal(keyword_data)
                competitor_signal = self._analyze_competitor_signal(competitor_data)
                seasonality_signal = self._analyze_seasonality_signal(seasonality_data, datetime.now())
                external_signal = self._analyze_external_signal(external_signals)
                
                # 3. 종합 예측
                prediction = self._combine_signals({
                    "sales": sales_signal,
                    "keyword": keyword_signal,
                    "competitor": competitor_signal,
                    "seasonality": seasonality_signal,
                    "external": external_signal
                })
                
                if prediction["confidence"] >= self.min_confidence:
                    # 4. 기회 탐색
                    opportunities = await self._identify_opportunities(
                        cat,
                        prediction,
                        sales_data,
                        keyword_data
                    )
                    
                    # 5. 트렌드 생성
                    trend = self._create_trend(
                        cat,
                        prediction,
                        opportunities,
                        horizon_days
                    )
                    
                    all_trends.append(trend)
            
            # 6. 교차 카테고리 트렌드 분석
            cross_trends = await self._analyze_cross_category_trends(all_trends)
            all_trends.extend(cross_trends)
            
            # 7. 우선순위 정렬
            all_trends.sort(
                key=lambda x: x.strength * x.confidence_level,
                reverse=True
            )
            
            return all_trends[:20]  # 상위 20개
            
        except Exception as e:
            logger.error(f"트렌드 예측 오류: {str(e)}")
            return []
    
    async def predict_product_performance(
        self,
        product_id: str,
        horizon_days: int = 30
    ) -> Dict[str, Any]:
        """
        상품별 성과 예측
        
        Args:
            product_id: 상품 ID
            horizon_days: 예측 기간
            
        Returns:
            성과 예측 결과
        """
        try:
            # 상품 정보 조회
            product = await self.storage.get("products", product_id)
            if not product:
                return {"error": "상품을 찾을 수 없습니다"}
            
            # 과거 판매 데이터
            sales_history = await self._get_product_sales_history(
                product_id,
                days=90
            )
            
            if len(sales_history) < 30:
                return {
                    "error": "예측을 위한 충분한 데이터가 없습니다",
                    "min_days_required": 30,
                    "actual_days": len(sales_history)
                }
            
            # 시계열 분석
            trend_analysis = self._analyze_time_series(sales_history)
            
            # 계절성 분석
            seasonality = await self._analyze_product_seasonality(product_id)
            
            # 키워드 트렌드
            keyword_trend = await self._analyze_product_keywords(product)
            
            # 경쟁 상황
            competition = await self._analyze_product_competition(product_id)
            
            # 예측 모델 적용
            forecast = self._forecast_sales(
                sales_history,
                trend_analysis,
                seasonality,
                keyword_trend,
                competition,
                horizon_days
            )
            
            # 리스크 분석
            risks = self._analyze_risks(
                product,
                trend_analysis,
                competition,
                forecast
            )
            
            # 추천사항
            recommendations = self._generate_recommendations(
                product,
                forecast,
                risks
            )
            
            return {
                "product_id": product_id,
                "product_name": product.get("name"),
                "current_performance": {
                    "daily_avg": trend_analysis["average"],
                    "trend": trend_analysis["trend"],
                    "volatility": trend_analysis["volatility"]
                },
                "forecast": forecast,
                "confidence": forecast["confidence"],
                "risks": risks,
                "recommendations": recommendations,
                "analyzed_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"상품 성과 예측 오류: {str(e)}")
            return {"error": str(e)}
    
    async def identify_emerging_trends(
        self,
        min_growth_rate: float = 50.0
    ) -> List[Dict[str, Any]]:
        """
        신흥 트렌드 식별
        
        Args:
            min_growth_rate: 최소 성장률 (%)
            
        Returns:
            신흥 트렌드 목록
        """
        try:
            emerging_trends = []
            
            # 1. 키워드 급상승 감지
            rising_keywords = await self._detect_rising_keywords(min_growth_rate)
            
            # 2. 신규 카테고리 성장 감지
            growing_categories = await self._detect_growing_categories(min_growth_rate)
            
            # 3. 가격대 변화 감지
            price_shifts = await self._detect_price_shifts()
            
            # 4. 브랜드/셀러 급부상 감지
            rising_sellers = await self._detect_rising_sellers(min_growth_rate)
            
            # 5. 패턴 매칭
            for keyword_data in rising_keywords:
                pattern = await self._match_trend_pattern(keyword_data)
                if pattern:
                    emerging_trends.append({
                        "type": "keyword",
                        "name": keyword_data["keyword"],
                        "growth_rate": keyword_data["growth_rate"],
                        "pattern": pattern,
                        "opportunities": await self._find_keyword_opportunities(
                            keyword_data["keyword"]
                        ),
                        "risk_level": self._assess_trend_risk(keyword_data),
                        "recommendation": self._generate_trend_recommendation(
                            "keyword",
                            keyword_data
                        )
                    })
            
            # 카테고리 트렌드
            for category_data in growing_categories:
                emerging_trends.append({
                    "type": "category",
                    "name": category_data["category"],
                    "growth_rate": category_data["growth_rate"],
                    "top_keywords": category_data.get("keywords", []),
                    "opportunities": await self._find_category_opportunities(
                        category_data["category"]
                    ),
                    "risk_level": self._assess_trend_risk(category_data),
                    "recommendation": self._generate_trend_recommendation(
                        "category",
                        category_data
                    )
                })
            
            # 정렬 및 반환
            emerging_trends.sort(
                key=lambda x: x["growth_rate"],
                reverse=True
            )
            
            return emerging_trends[:30]
            
        except Exception as e:
            logger.error(f"신흥 트렌드 식별 오류: {str(e)}")
            return []
    
    async def _get_active_categories(self) -> List[str]:
        """활성 카테고리 목록 조회"""
        products = await self.storage.list(
            "products",
            filters={"status": "active"}
        )
        categories = list(set(p.get("category_name") for p in products if p.get("category_name")))
        return categories
    
    async def _collect_sales_data(
        self,
        category: str,
        days: int = 90
    ) -> List[Tuple[datetime, int, Decimal]]:
        """판매 데이터 수집"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        daily_data = []
        current = start_date
        
        while current <= end_date:
            next_day = current + timedelta(days=1)
            
            orders = await self.storage.list(
                "orders",
                filters={
                    "status": {"$in": ["delivered", "shipped"]},
                    "order_date": {
                        "$gte": current,
                        "$lt": next_day
                    }
                }
            )
            
            day_sales = 0
            day_revenue = Decimal("0")
            
            for order in orders:
                for item in order.get("items", []):
                    product = await self.storage.get(
                        "products",
                        item.get("product_id")
                    )
                    if product and product.get("category_name") == category:
                        day_sales += item.get("quantity", 0)
                        day_revenue += Decimal(str(item.get("total_price", 0)))
            
            daily_data.append((current, day_sales, day_revenue))
            current = next_day
        
        return daily_data
    
    async def _collect_keyword_data(
        self,
        category: str
    ) -> Dict[str, Any]:
        """키워드 데이터 수집"""
        # 카테고리 관련 키워드
        keywords = await self.keyword_researcher.find_opportunity_keywords(
            category,
            min_volume=100,
            max_competition="high"
        )
        
        # 키워드별 트렌드
        keyword_trends = {}
        for kw_data in keywords[:20]:  # 상위 20개
            keyword = kw_data["keyword"]
            metrics = kw_data["metrics"]
            
            # 30일 트렌드
            trend_data = await self.keyword_researcher.track_keyword_trends(
                [keyword],
                days=30
            )
            
            keyword_trends[keyword] = {
                "metrics": metrics,
                "trend": trend_data["keyword_trends"].get(keyword, {})
            }
        
        return keyword_trends
    
    async def _collect_competitor_data(
        self,
        category: str
    ) -> List[Dict[str, Any]]:
        """경쟁사 데이터 수집"""
        # 카테고리 상품 샘플
        products = await self.storage.list(
            "products",
            filters={"category_name": category},
            limit=10
        )
        
        competitor_data = []
        for product in products:
            competitors = await self.competitor_monitor.identify_competitors(
                product["id"]
            )
            
            for comp in competitors[:5]:  # 상위 5개
                price_monitor = await self.competitor_monitor.monitor_competitor_prices(
                    product["id"],
                    [comp]
                )
                
                competitor_data.append({
                    "competitor": comp,
                    "price_data": price_monitor
                })
        
        return competitor_data
    
    async def _analyze_seasonality(
        self,
        category: str
    ) -> Dict[str, float]:
        """계절성 분석"""
        # 카테고리 대표 상품들의 계절성
        products = await self.storage.list(
            "products",
            filters={"category_name": category},
            limit=20
        )
        
        all_seasonality = defaultdict(list)
        
        for product in products:
            seasonality = await self.sales_analyzer.calculate_seasonality(
                product["id"]
            )
            
            for month, index in seasonality.items():
                all_seasonality[month].append(index)
        
        # 평균 계절성 지수
        avg_seasonality = {}
        for month, indices in all_seasonality.items():
            if indices:
                avg_seasonality[month] = sum(indices) / len(indices)
            else:
                avg_seasonality[month] = 1.0
        
        return avg_seasonality
    
    async def _collect_external_signals(
        self,
        category: str
    ) -> Dict[str, Any]:
        """외부 신호 수집 (SNS 트렌드, 뉴스 등)"""
        # 실제로는 외부 API 연동
        # 여기서는 시뮬레이션
        
        return {
            "social_mentions": await self._get_social_mentions(category),
            "news_sentiment": await self._get_news_sentiment(category),
            "search_trend": await self._get_search_trend(category)
        }
    
    def _analyze_sales_signal(
        self,
        sales_data: List[Tuple[datetime, int, Decimal]]
    ) -> Dict[str, Any]:
        """판매 신호 분석"""
        if len(sales_data) < 7:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        # 이동평균
        sales_values = [s[1] for s in sales_data]
        ma7 = []
        ma30 = []
        
        for i in range(6, len(sales_values)):
            ma7.append(sum(sales_values[i-6:i+1]) / 7)
        
        for i in range(29, len(sales_values)):
            ma30.append(sum(sales_values[i-29:i+1]) / 30)
        
        # 트렌드 방향
        if len(ma7) >= 2:
            recent_trend = (ma7[-1] - ma7[-7]) / (ma7[-7] + 1) if len(ma7) >= 7 else 0
        else:
            recent_trend = 0
        
        # 강도 계산
        avg_sales = sum(sales_values) / len(sales_values)
        if avg_sales > 0:
            strength = min(100, abs(recent_trend) * 100)
        else:
            strength = 0
        
        # 방향 결정
        if recent_trend > 0.1:
            direction = TrendDirection.UP
        elif recent_trend < -0.1:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE
        
        # 신뢰도 (데이터 포인트와 변동성 기반)
        if len(sales_values) > 1:
            cv = statistics.stdev(sales_values) / (avg_sales + 1)
            confidence = max(0, min(100, (1 - cv) * 100 * (len(sales_data) / 90)))
        else:
            confidence = 0
        
        return {
            "strength": strength,
            "direction": direction,
            "confidence": confidence,
            "recent_trend": recent_trend
        }
    
    def _analyze_keyword_signal(
        self,
        keyword_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """키워드 신호 분석"""
        if not keyword_data:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        # 상승 키워드 비율
        rising_count = 0
        total_count = 0
        avg_strength = 0
        
        for keyword, data in keyword_data.items():
            trend = data.get("trend", {})
            if trend.get("trend") == TrendDirection.UP:
                rising_count += 1
                avg_strength += trend.get("trend_strength", 0)
            total_count += 1
        
        if total_count == 0:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        rising_ratio = rising_count / total_count
        
        # 방향 결정
        if rising_ratio > 0.6:
            direction = TrendDirection.UP
        elif rising_ratio < 0.3:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE
        
        # 강도
        strength = (rising_ratio * 100 + avg_strength) / 2 if rising_count > 0 else 0
        
        # 신뢰도
        confidence = min(100, total_count * 5)  # 키워드 수에 비례
        
        return {
            "strength": strength,
            "direction": direction,
            "confidence": confidence,
            "rising_keywords": rising_count
        }
    
    def _analyze_competitor_signal(
        self,
        competitor_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """경쟁사 신호 분석"""
        if not competitor_data:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        # 가격 변동 분석
        price_changes = []
        
        for data in competitor_data:
            price_info = data.get("price_data", {})
            changes = price_info.get("price_changes", [])
            price_changes.extend(changes)
        
        if not price_changes:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "confidence": 50.0
            }
        
        # 평균 가격 변동
        avg_change = sum(c["change_rate"] for c in price_changes) / len(price_changes)
        
        # 방향 (가격 하락 = 경쟁 심화 = 부정적 신호)
        if avg_change < -5:
            direction = TrendDirection.DOWN
        elif avg_change > 5:
            direction = TrendDirection.UP
        else:
            direction = TrendDirection.STABLE
        
        # 강도
        strength = min(100, abs(avg_change) * 2)
        
        # 신뢰도
        confidence = min(100, len(price_changes) * 10)
        
        return {
            "strength": strength,
            "direction": direction,
            "confidence": confidence,
            "avg_price_change": avg_change
        }
    
    def _analyze_seasonality_signal(
        self,
        seasonality_data: Dict[str, float],
        current_date: datetime
    ) -> Dict[str, Any]:
        """계절성 신호 분석"""
        current_month = str(current_date.month)
        next_month = str((current_date.month % 12) + 1)
        
        current_index = seasonality_data.get(current_month, 1.0)
        next_index = seasonality_data.get(next_month, 1.0)
        
        # 계절성 변화
        seasonal_change = (next_index - current_index) / current_index
        
        # 방향
        if seasonal_change > 0.1:
            direction = TrendDirection.UP
        elif seasonal_change < -0.1:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE
        
        # 강도
        strength = min(100, abs(seasonal_change) * 100)
        
        # 신뢰도 (계절성 패턴의 일관성)
        if len(seasonality_data) == 12:
            indices = list(seasonality_data.values())
            cv = statistics.stdev(indices) / statistics.mean(indices)
            confidence = max(0, min(100, (1 - cv) * 100))
        else:
            confidence = 50.0
        
        return {
            "strength": strength,
            "direction": direction,
            "confidence": confidence,
            "seasonal_factor": next_index
        }
    
    def _analyze_external_signal(
        self,
        external_signals: Dict[str, Any]
    ) -> Dict[str, Any]:
        """외부 신호 분석"""
        # SNS 언급량
        social_trend = external_signals.get("social_mentions", {}).get("trend", 0)
        
        # 뉴스 감성
        news_sentiment = external_signals.get("news_sentiment", {}).get("score", 0)
        
        # 검색 트렌드
        search_trend = external_signals.get("search_trend", {}).get("growth", 0)
        
        # 종합 점수
        composite_score = (social_trend + news_sentiment + search_trend) / 3
        
        # 방향
        if composite_score > 20:
            direction = TrendDirection.UP
        elif composite_score < -20:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE
        
        # 강도
        strength = min(100, abs(composite_score))
        
        # 신뢰도
        confidence = 70.0  # 외부 신호는 기본적으로 중간 신뢰도
        
        return {
            "strength": strength,
            "direction": direction,
            "confidence": confidence
        }
    
    def _combine_signals(
        self,
        signals: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """신호 종합"""
        # 가중 평균 계산
        total_strength = 0
        total_confidence = 0
        direction_scores = {"up": 0, "down": 0, "stable": 0}
        
        for signal_type, signal_data in signals.items():
            weight = self.signal_weights.get(signal_type, 0.1)
            
            total_strength += signal_data["strength"] * weight
            total_confidence += signal_data["confidence"] * weight
            
            # 방향별 점수
            direction = signal_data["direction"]
            if direction == TrendDirection.UP:
                direction_scores["up"] += weight * signal_data["strength"]
            elif direction == TrendDirection.DOWN:
                direction_scores["down"] += weight * signal_data["strength"]
            else:
                direction_scores["stable"] += weight * signal_data["strength"]
        
        # 최종 방향 결정
        max_direction = max(direction_scores, key=direction_scores.get)
        if max_direction == "up":
            final_direction = TrendDirection.UP
        elif max_direction == "down":
            final_direction = TrendDirection.DOWN
        else:
            final_direction = TrendDirection.STABLE
        
        # 예측 변동성
        volatility = statistics.stdev([s["strength"] for s in signals.values()])
        
        return {
            "strength": total_strength,
            "direction": final_direction,
            "confidence": total_confidence,
            "volatility": volatility,
            "signals": signals
        }
    
    async def _identify_opportunities(
        self,
        category: str,
        prediction: Dict[str, Any],
        sales_data: List[Tuple[datetime, int, Decimal]],
        keyword_data: Dict[str, Any]
    ) -> List[ProductOpportunity]:
        """기회 식별"""
        opportunities = []
        
        # 상승 트렌드인 경우에만 기회 탐색
        if prediction["direction"] != TrendDirection.UP:
            return opportunities
        
        # 유망 키워드 기반 기회
        for keyword, data in keyword_data.items():
            metrics = data["metrics"]
            if (metrics.competition_level in ["low", "medium"] and
                metrics.trend == TrendDirection.UP):
                
                opportunity = ProductOpportunity(
                    opportunity_id=f"OPP_{category}_{keyword}_{datetime.now().strftime('%Y%m%d')}",
                    opportunity_score=self._calculate_opportunity_score(
                        metrics,
                        prediction["strength"]
                    ),
                    product_name=f"{keyword} 관련 상품",
                    category=category,
                    keywords=[keyword] + metrics.related_keywords[:3],
                    market_demand="high" if metrics.search_volume > 10000 else "medium",
                    competition_level=metrics.competition_level,
                    entry_barrier="low" if metrics.competition_level == "low" else "medium",
                    estimated_price=metrics.average_price,
                    estimated_cost=metrics.average_price * Decimal("0.6"),  # 40% 마진 가정
                    estimated_margin=metrics.average_price * Decimal("0.4"),
                    estimated_monthly_sales=int(
                        metrics.search_volume * (metrics.conversion_rate or 0.02) * 0.1
                    ),
                    supplier_count=await self._count_suppliers(keyword),
                    recommended_suppliers=await self._recommend_suppliers(keyword),
                    risks=self._identify_opportunity_risks(metrics, prediction),
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=30)
                )
                
                opportunities.append(opportunity)
        
        # 정렬
        opportunities.sort(
            key=lambda x: x.opportunity_score,
            reverse=True
        )
        
        return opportunities[:10]
    
    def _create_trend(
        self,
        category: str,
        prediction: Dict[str, Any],
        opportunities: List[ProductOpportunity],
        horizon_days: int
    ) -> MarketTrend:
        """트렌드 생성"""
        # 트렌딩 키워드 추출
        trending_keywords = []
        for opp in opportunities:
            trending_keywords.extend(opp.keywords)
        trending_keywords = list(set(trending_keywords))[:20]
        
        # 트렌딩 상품
        trending_products = [
            {
                "name": opp.product_name,
                "score": opp.opportunity_score,
                "estimated_sales": opp.estimated_monthly_sales
            }
            for opp in opportunities[:5]
        ]
        
        return MarketTrend(
            trend_id=f"TREND_{category}_{datetime.now().strftime('%Y%m%d%H%M')}",
            name=f"{category} {prediction['direction']} 트렌드",
            category=category,
            strength=prediction["strength"],
            direction=prediction["direction"],
            momentum=prediction.get("volatility", 0),
            trending_keywords=trending_keywords,
            trending_products=trending_products,
            forecast_period=horizon_days,
            forecast_direction=prediction["direction"],
            confidence_level=prediction["confidence"],
            analyzed_at=datetime.now(),
            data_points=90  # 90일 데이터 기반
        )
    
    async def _analyze_cross_category_trends(
        self,
        category_trends: List[MarketTrend]
    ) -> List[MarketTrend]:
        """교차 카테고리 트렌드 분석"""
        cross_trends = []
        
        # 공통 키워드 찾기
        keyword_categories = defaultdict(list)
        
        for trend in category_trends:
            for keyword in trend.trending_keywords:
                keyword_categories[keyword].append(trend.category)
        
        # 2개 이상 카테고리에 나타나는 키워드
        cross_keywords = {
            k: v for k, v in keyword_categories.items()
            if len(v) >= 2
        }
        
        if cross_keywords:
            # 메가 트렌드 생성
            mega_trend = MarketTrend(
                trend_id=f"TREND_MEGA_{datetime.now().strftime('%Y%m%d%H%M')}",
                name="크로스 카테고리 메가 트렌드",
                category="ALL",
                strength=sum(t.strength for t in category_trends) / len(category_trends),
                direction=TrendDirection.UP,  # 교차 트렌드는 보통 상승
                momentum=80.0,
                trending_keywords=list(cross_keywords.keys())[:20],
                trending_products=[],
                forecast_period=30,
                forecast_direction=TrendDirection.UP,
                confidence_level=85.0,
                analyzed_at=datetime.now(),
                data_points=sum(t.data_points for t in category_trends)
            )
            
            cross_trends.append(mega_trend)
        
        return cross_trends
    
    async def _get_product_sales_history(
        self,
        product_id: str,
        days: int
    ) -> List[Tuple[datetime, int]]:
        """상품 판매 이력 조회"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        daily_sales = []
        current = start_date
        
        while current <= end_date:
            next_day = current + timedelta(days=1)
            
            orders = await self.storage.list(
                "orders",
                filters={
                    "status": {"$in": ["delivered", "shipped"]},
                    "order_date": {
                        "$gte": current,
                        "$lt": next_day
                    }
                }
            )
            
            day_sales = 0
            for order in orders:
                for item in order.get("items", []):
                    if item.get("product_id") == product_id:
                        day_sales += item.get("quantity", 0)
            
            daily_sales.append((current, day_sales))
            current = next_day
        
        return daily_sales
    
    def _analyze_time_series(
        self,
        sales_history: List[Tuple[datetime, int]]
    ) -> Dict[str, Any]:
        """시계열 분석"""
        if len(sales_history) < 2:
            return {
                "trend": TrendDirection.STABLE,
                "average": 0,
                "volatility": 0,
                "slope": 0
            }
        
        values = [s[1] for s in sales_history]
        
        # 평균
        average = sum(values) / len(values)
        
        # 변동성
        if average > 0:
            volatility = statistics.stdev(values) / average
        else:
            volatility = 0
        
        # 추세 (선형 회귀)
        n = len(values)
        x = list(range(n))
        
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        if n * sum_x2 - sum_x ** 2 == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        # 트렌드 방향
        if slope > 0.1:
            trend = TrendDirection.UP
        elif slope < -0.1:
            trend = TrendDirection.DOWN
        else:
            trend = TrendDirection.STABLE
        
        return {
            "trend": trend,
            "average": average,
            "volatility": volatility,
            "slope": slope
        }
    
    async def _analyze_product_seasonality(
        self,
        product_id: str
    ) -> Dict[str, float]:
        """상품 계절성 분석"""
        return await self.sales_analyzer.calculate_seasonality(product_id)
    
    async def _analyze_product_keywords(
        self,
        product: Dict[str, Any]
    ) -> Dict[str, Any]:
        """상품 키워드 트렌드 분석"""
        # 상품명에서 주요 키워드 추출
        keywords = product.get("name", "").split()[:3]
        
        if not keywords:
            return {"trend": TrendDirection.STABLE, "strength": 0}
        
        # 키워드 트렌드 조회
        trends = await self.keyword_researcher.track_keyword_trends(
            keywords,
            days=30
        )
        
        # 평균 트렌드
        keyword_trends = trends.get("keyword_trends", {})
        
        up_count = sum(1 for k, v in keyword_trends.items() if v.get("trend") == TrendDirection.UP)
        down_count = sum(1 for k, v in keyword_trends.items() if v.get("trend") == TrendDirection.DOWN)
        
        if up_count > down_count:
            return {"trend": TrendDirection.UP, "strength": 70}
        elif down_count > up_count:
            return {"trend": TrendDirection.DOWN, "strength": 70}
        else:
            return {"trend": TrendDirection.STABLE, "strength": 50}
    
    async def _analyze_product_competition(
        self,
        product_id: str
    ) -> Dict[str, Any]:
        """상품 경쟁 분석"""
        competitors = await self.competitor_monitor.identify_competitors(product_id)
        
        if not competitors:
            return {"level": "low", "risk": 20}
        
        # 경쟁 강도
        avg_rating = sum(c.average_rating or 0 for c in competitors) / len(competitors)
        total_reviews = sum(c.review_count or 0 for c in competitors)
        
        if total_reviews > 1000 and avg_rating > 4.5:
            return {"level": "high", "risk": 80}
        elif total_reviews > 500 or avg_rating > 4.0:
            return {"level": "medium", "risk": 50}
        else:
            return {"level": "low", "risk": 20}
    
    def _forecast_sales(
        self,
        sales_history: List[Tuple[datetime, int]],
        trend_analysis: Dict[str, Any],
        seasonality: Dict[str, float],
        keyword_trend: Dict[str, Any],
        competition: Dict[str, Any],
        horizon_days: int
    ) -> Dict[str, Any]:
        """판매량 예측"""
        if len(sales_history) < 30:
            return {
                "error": "예측을 위한 충분한 데이터가 없습니다",
                "confidence": 0
            }
        
        # 기본 예측 (이동평균 + 트렌드)
        recent_avg = sum(s[1] for s in sales_history[-7:]) / 7
        trend_factor = 1 + (trend_analysis["slope"] * horizon_days / 100)
        
        # 계절성 조정
        current_month = datetime.now().month
        target_month = (current_month + horizon_days // 30) % 12 + 1
        seasonal_factor = seasonality.get(str(target_month), 1.0)
        
        # 키워드 트렌드 조정
        keyword_factor = 1.0
        if keyword_trend["trend"] == TrendDirection.UP:
            keyword_factor = 1.1
        elif keyword_trend["trend"] == TrendDirection.DOWN:
            keyword_factor = 0.9
        
        # 경쟁 조정
        competition_factor = 1.0
        if competition["level"] == "high":
            competition_factor = 0.8
        elif competition["level"] == "low":
            competition_factor = 1.2
        
        # 최종 예측
        forecast_daily = recent_avg * trend_factor * seasonal_factor * keyword_factor * competition_factor
        forecast_total = forecast_daily * horizon_days
        
        # 신뢰 구간
        volatility = trend_analysis["volatility"]
        lower_bound = forecast_total * (1 - volatility)
        upper_bound = forecast_total * (1 + volatility)
        
        # 신뢰도
        confidence = max(0, min(100, 100 - volatility * 100))
        
        return {
            "daily_average": forecast_daily,
            "total": forecast_total,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence": confidence,
            "factors": {
                "trend": trend_factor,
                "seasonality": seasonal_factor,
                "keyword": keyword_factor,
                "competition": competition_factor
            }
        }
    
    def _analyze_risks(
        self,
        product: Dict[str, Any],
        trend_analysis: Dict[str, Any],
        competition: Dict[str, Any],
        forecast: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """리스크 분석"""
        risks = []
        
        # 트렌드 리스크
        if trend_analysis["trend"] == TrendDirection.DOWN:
            risks.append({
                "type": "trend",
                "level": "high",
                "description": "하락 트렌드가 지속되고 있습니다",
                "impact": "판매량 감소 예상"
            })
        
        # 경쟁 리스크
        if competition["level"] == "high":
            risks.append({
                "type": "competition",
                "level": "high",
                "description": "경쟁이 매우 치열합니다",
                "impact": "시장 점유율 확보 어려움"
            })
        
        # 변동성 리스크
        if trend_analysis["volatility"] > 0.5:
            risks.append({
                "type": "volatility",
                "level": "medium",
                "description": "판매량 변동성이 큽니다",
                "impact": "예측 정확도 저하"
            })
        
        # 재고 리스크
        if product.get("stock", 0) < forecast.get("total", 0) * 0.5:
            risks.append({
                "type": "inventory",
                "level": "medium",
                "description": "예상 판매량 대비 재고 부족",
                "impact": "품절 가능성"
            })
        
        return risks
    
    def _generate_recommendations(
        self,
        product: Dict[str, Any],
        forecast: Dict[str, Any],
        risks: List[Dict[str, Any]]
    ) -> List[str]:
        """추천사항 생성"""
        recommendations = []
        
        # 예측 기반 추천
        if forecast.get("confidence", 0) > 70:
            if forecast.get("daily_average", 0) > product.get("avg_daily_sales", 0) * 1.5:
                recommendations.append("판매량 증가 예상 - 재고 확충 필요")
            elif forecast.get("daily_average", 0) < product.get("avg_daily_sales", 0) * 0.5:
                recommendations.append("판매량 감소 예상 - 프로모션 검토 필요")
        
        # 리스크 기반 추천
        for risk in risks:
            if risk["type"] == "trend" and risk["level"] == "high":
                recommendations.append("상품 리뉴얼 또는 신상품 개발 검토")
            elif risk["type"] == "competition" and risk["level"] == "high":
                recommendations.append("차별화 전략 수립 필요 (가격, 품질, 서비스)")
            elif risk["type"] == "inventory":
                recommendations.append("안전재고 수준 상향 조정 권장")
        
        # 계절성 추천
        if forecast.get("factors", {}).get("seasonality", 1.0) > 1.2:
            recommendations.append("성수기 대비 마케팅 강화")
        elif forecast.get("factors", {}).get("seasonality", 1.0) < 0.8:
            recommendations.append("비수기 할인 프로모션 검토")
        
        return recommendations[:5]
    
    async def _detect_rising_keywords(
        self,
        min_growth_rate: float
    ) -> List[Dict[str, Any]]:
        """급상승 키워드 감지"""
        rising_keywords = []
        
        # 모든 활성 키워드 조회
        keyword_metrics = await self.storage.list(
            "keyword_metrics",
            filters={
                "analyzed_at": {
                    "$gte": datetime.now() - timedelta(days=7)
                }
            }
        )
        
        for metric in keyword_metrics:
            # 이전 데이터와 비교
            prev_metrics = await self.storage.list(
                "keyword_metrics",
                filters={
                    "keyword": metric["keyword"],
                    "analyzed_at": {
                        "$gte": datetime.now() - timedelta(days=14),
                        "$lt": datetime.now() - timedelta(days=7)
                    }
                }
            )
            
            if prev_metrics:
                prev_volume = prev_metrics[0].get("search_volume", 0)
                curr_volume = metric.get("search_volume", 0)
                
                if prev_volume > 0:
                    growth_rate = ((curr_volume - prev_volume) / prev_volume) * 100
                    
                    if growth_rate >= min_growth_rate:
                        rising_keywords.append({
                            "keyword": metric["keyword"],
                            "growth_rate": growth_rate,
                            "current_volume": curr_volume,
                            "previous_volume": prev_volume,
                            "competition": metric.get("competition_level"),
                            "trend": metric.get("trend")
                        })
        
        return rising_keywords
    
    async def _detect_growing_categories(
        self,
        min_growth_rate: float
    ) -> List[Dict[str, Any]]:
        """성장 카테고리 감지"""
        growing_categories = []
        
        categories = await self._get_active_categories()
        
        for category in categories:
            # 최근 30일 vs 이전 30일 판매량
            recent_metrics = await self.sales_analyzer.analyze_category_sales(
                category,
                datetime.now() - timedelta(days=30),
                datetime.now()
            )
            
            previous_metrics = await self.sales_analyzer.analyze_category_sales(
                category,
                datetime.now() - timedelta(days=60),
                datetime.now() - timedelta(days=30)
            )
            
            if recent_metrics and previous_metrics:
                recent_sales = recent_metrics.get("total_sales", 0)
                previous_sales = previous_metrics.get("total_sales", 0)
                
                if previous_sales > 0:
                    growth_rate = ((recent_sales - previous_sales) / previous_sales) * 100
                    
                    if growth_rate >= min_growth_rate:
                        # 주요 키워드 추출
                        keywords = []
                        for pm in recent_metrics.get("product_metrics", [])[:10]:
                            product_name = pm.get("product_name", "")
                            keywords.extend(product_name.split()[:2])
                        
                        growing_categories.append({
                            "category": category,
                            "growth_rate": growth_rate,
                            "recent_sales": recent_sales,
                            "previous_sales": previous_sales,
                            "keywords": list(set(keywords))[:10]
                        })
        
        return growing_categories
    
    async def _detect_price_shifts(self) -> List[Dict[str, Any]]:
        """가격대 변화 감지"""
        price_shifts = []
        
        # 카테고리별 가격 변화 분석
        categories = await self._get_active_categories()
        
        for category in categories[:10]:  # 상위 10개 카테고리
            products = await self.storage.list(
                "products",
                filters={"category_name": category}
            )
            
            if len(products) < 10:
                continue
            
            # 현재 가격 분포
            current_prices = [Decimal(str(p.get("price", 0))) for p in products]
            avg_price = sum(current_prices) / len(current_prices)
            
            # 가격 변화 추적 (실제로는 히스토리 데이터 필요)
            # 여기서는 시뮬레이션
            price_change = 0.0  # 실제로는 계산 필요
            
            if abs(price_change) > 10:
                price_shifts.append({
                    "category": category,
                    "price_change": price_change,
                    "current_avg_price": avg_price,
                    "direction": "up" if price_change > 0 else "down"
                })
        
        return price_shifts
    
    async def _detect_rising_sellers(
        self,
        min_growth_rate: float
    ) -> List[Dict[str, Any]]:
        """급부상 셀러 감지"""
        # 실제로는 셀러별 판매 추적 필요
        # 여기서는 빈 리스트 반환
        return []
    
    async def _match_trend_pattern(
        self,
        trend_data: Dict[str, Any]
    ) -> Optional[str]:
        """트렌드 패턴 매칭"""
        growth_rate = trend_data.get("growth_rate", 0)
        volume = trend_data.get("current_volume", 0)
        competition = trend_data.get("competition", "medium")
        
        # 패턴 정의
        if growth_rate > 100 and volume > 10000 and competition == "low":
            return "골든 기회"
        elif growth_rate > 50 and competition in ["low", "medium"]:
            return "유망 트렌드"
        elif growth_rate > 30:
            return "관찰 필요"
        else:
            return None
    
    async def _find_keyword_opportunities(
        self,
        keyword: str
    ) -> List[str]:
        """키워드 관련 기회 찾기"""
        opportunities = []
        
        # 키워드 메트릭스
        metrics = await self.keyword_researcher.research_keyword(keyword)
        
        if metrics.competition_level == "low":
            opportunities.append("낮은 경쟁도 - 진입 용이")
        
        if metrics.search_volume > 5000:
            opportunities.append("높은 검색량 - 수요 확실")
        
        if metrics.trend == TrendDirection.UP:
            opportunities.append("상승 트렌드 - 성장 가능성")
        
        if metrics.product_count < 50:
            opportunities.append("적은 상품 수 - 시장 공백")
        
        return opportunities
    
    async def _find_category_opportunities(
        self,
        category: str
    ) -> List[str]:
        """카테고리 관련 기회 찾기"""
        opportunities = []
        
        # 카테고리 분석
        analysis = await self.sales_analyzer.analyze_category_sales(
            category,
            datetime.now() - timedelta(days=30),
            datetime.now()
        )
        
        if analysis.get("total_products", 0) < 100:
            opportunities.append("상품 다양성 부족 - 니치 시장")
        
        price_dist = analysis.get("price_distribution", {})
        if price_dist:
            avg_price = price_dist.get("avg", 0)
            if avg_price > 50000:
                opportunities.append("고가 시장 - 높은 마진")
        
        return opportunities
    
    def _assess_trend_risk(
        self,
        trend_data: Dict[str, Any]
    ) -> str:
        """트렌드 리스크 평가"""
        growth_rate = trend_data.get("growth_rate", 0)
        
        if growth_rate > 200:
            return "high"  # 너무 빠른 성장은 거품 가능성
        elif growth_rate > 100:
            return "medium"
        else:
            return "low"
    
    def _generate_trend_recommendation(
        self,
        trend_type: str,
        trend_data: Dict[str, Any]
    ) -> str:
        """트렌드 추천사항 생성"""
        if trend_type == "keyword":
            if trend_data.get("competition") == "low":
                return "즉시 진입 권장 - 선점 효과 극대화"
            elif trend_data.get("growth_rate", 0) > 100:
                return "빠른 상품 개발 필요 - 트렌드 활용"
            else:
                return "지속 모니터링 권장"
        
        elif trend_type == "category":
            if trend_data.get("growth_rate", 0) > 50:
                return "카테고리 확장 검토 - 상품군 다양화"
            else:
                return "선별적 진입 권장"
        
        return "추가 분석 필요"
    
    def _calculate_opportunity_score(
        self,
        metrics: Any,
        trend_strength: float
    ) -> float:
        """기회 점수 계산"""
        score = 0.0
        
        # 검색량 점수 (30점)
        if metrics.search_volume > 10000:
            score += 30
        elif metrics.search_volume > 5000:
            score += 20
        elif metrics.search_volume > 1000:
            score += 10
        
        # 경쟁도 점수 (30점)
        if metrics.competition_level == "low":
            score += 30
        elif metrics.competition_level == "medium":
            score += 15
        
        # 트렌드 점수 (20점)
        score += min(20, trend_strength / 5)
        
        # 전환율 점수 (20점)
        if metrics.conversion_rate:
            score += min(20, metrics.conversion_rate * 400)
        
        return min(100, score)
    
    async def _count_suppliers(self, keyword: str) -> int:
        """키워드 관련 공급사 수 계산"""
        # 실제로는 공급사 상품 검색
        # 여기서는 추정값
        return 5
    
    async def _recommend_suppliers(self, keyword: str) -> List[str]:
        """키워드 관련 추천 공급사"""
        # 실제로는 공급사별 상품 매칭
        # 여기서는 기본값
        return ["domeme", "ownerclan", "zentrade"]
    
    def _identify_opportunity_risks(
        self,
        metrics: Any,
        prediction: Dict[str, Any]
    ) -> List[str]:
        """기회 리스크 식별"""
        risks = []
        
        if metrics.competition_level == "high":
            risks.append("높은 경쟁도")
        
        if prediction.get("volatility", 0) > 50:
            risks.append("높은 변동성")
        
        if metrics.product_count > 1000:
            risks.append("시장 포화")
        
        return risks
    
    async def _get_social_mentions(self, category: str) -> Dict[str, Any]:
        """SNS 언급량 조회 (시뮬레이션)"""
        # 실제로는 SNS API 연동
        return {
            "count": 1000,
            "trend": 20,  # 20% 증가
            "sentiment": 0.7  # 긍정적
        }
    
    async def _get_news_sentiment(self, category: str) -> Dict[str, Any]:
        """뉴스 감성 분석 (시뮬레이션)"""
        # 실제로는 뉴스 API 연동
        return {
            "score": 15,  # -100 ~ 100
            "article_count": 50
        }
    
    async def _get_search_trend(self, category: str) -> Dict[str, Any]:
        """검색 트렌드 조회 (시뮬레이션)"""
        # 실제로는 검색 트렌드 API
        return {
            "growth": 25,  # 25% 성장
            "volume_index": 80  # 0-100
        }