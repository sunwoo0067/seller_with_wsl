"""
소싱 인텔리전스 대시보드
통합 분석 및 시각화 인터페이스
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from dropshipping.models.sourcing import (
    MarketTrend,
    ProductOpportunity,
    SalesMetrics,
    SourcingReport,
    TrendDirection,
)
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.sourcing.trend_predictor import TrendPredictor
from dropshipping.storage.base import BaseStorage


class SourcingDashboard:
    """소싱 대시보드"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 대시보드 설정
        """
        self.storage = storage
        self.config = config or {}

        # 분석 모듈
        self.sales_analyzer = SalesAnalyzer(storage, config)
        self.competitor_monitor = CompetitorMonitor(storage, config)
        self.keyword_researcher = KeywordResearcher(storage, config)
        self.trend_predictor = TrendPredictor(storage, config)

        # 대시보드 설정
        self.refresh_interval = self.config.get("refresh_interval", 3600)  # 1시간
        self.report_retention_days = self.config.get("report_retention_days", 30)

        # 캐시
        self._dashboard_cache = {}

    async def get_overview(self) -> Dict[str, Any]:
        """
        대시보드 개요

        Returns:
            전체 현황 요약
        """
        try:
            # 캐시 확인
            cache_key = "overview"
            if self._is_cache_valid(cache_key):
                return self._dashboard_cache[cache_key]["data"]

            # 기간 설정
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            prev_start = start_date - timedelta(days=30)

            # 1. 전체 판매 현황
            current_sales = await self._get_total_sales(start_date, end_date)
            previous_sales = await self._get_total_sales(prev_start, start_date)

            sales_growth = self._calculate_growth_rate(
                current_sales["total_revenue"], previous_sales["total_revenue"]
            )

            # 2. 시장 트렌드
            market_trends = await self.trend_predictor.predict_trends(horizon_days=30)

            # 3. 주요 기회
            top_opportunities = await self._get_top_opportunities()

            # 4. 경쟁 현황
            competition_summary = await self._get_competition_summary()

            # 5. 키워드 인사이트
            keyword_insights = await self._get_keyword_insights()

            # 6. 알림 및 액션 아이템
            alerts = await self._generate_alerts(sales_growth, market_trends, competition_summary)

            overview = {
                "summary": {
                    "total_revenue": current_sales["total_revenue"],
                    "total_orders": current_sales["total_orders"],
                    "growth_rate": sales_growth,
                    "active_products": await self._count_active_products(),
                    "tracked_competitors": await self._count_tracked_competitors(),
                },
                "sales_performance": {
                    "current_period": current_sales,
                    "previous_period": previous_sales,
                    "trend": self._determine_trend(sales_growth),
                    "top_categories": current_sales["top_categories"][:5],
                    "top_products": current_sales["top_products"][:10],
                },
                "market_trends": [
                    {
                        "id": trend.trend_id,
                        "name": trend.name,
                        "category": trend.category,
                        "strength": trend.strength,
                        "direction": trend.direction,
                        "confidence": trend.confidence_level,
                        "keywords": trend.trending_keywords[:5],
                    }
                    for trend in market_trends[:5]
                ],
                "opportunities": [
                    {
                        "id": opp.opportunity_id,
                        "name": opp.product_name,
                        "score": opp.opportunity_score,
                        "category": opp.category,
                        "estimated_revenue": float(
                            opp.estimated_price * opp.estimated_monthly_sales
                        ),
                        "competition": opp.competition_level,
                    }
                    for opp in top_opportunities[:5]
                ],
                "competition": competition_summary,
                "keywords": keyword_insights,
                "alerts": alerts[:10],
                "last_updated": datetime.now(),
            }

            # 캐시 저장
            self._dashboard_cache[cache_key] = {"data": overview, "timestamp": datetime.now()}

            return overview

        except Exception as e:
            logger.error(f"대시보드 개요 생성 오류: {str(e)}")
            return {"error": str(e)}

    async def get_sales_dashboard(self, period_days: int = 30) -> Dict[str, Any]:
        """
        판매 대시보드

        Args:
            period_days: 분석 기간

        Returns:
            판매 분석 대시보드
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)

            # 1. 기간별 판매 추이
            daily_sales = await self._get_daily_sales_trend(start_date, end_date)

            # 2. 카테고리별 성과
            category_performance = await self._get_category_performance(start_date, end_date)

            # 3. 상품별 성과
            product_performance = await self._get_product_performance(start_date, end_date)

            # 4. 시간대별 분석
            hourly_pattern = await self._analyze_hourly_pattern(start_date, end_date)

            # 5. 고객 분석
            customer_analysis = await self._analyze_customers(start_date, end_date)

            return {
                "period": {"start": start_date, "end": end_date, "days": period_days},
                "daily_trend": daily_sales,
                "categories": category_performance,
                "products": product_performance,
                "patterns": {
                    "hourly": hourly_pattern,
                    "weekday": await self._analyze_weekday_pattern(start_date, end_date),
                },
                "customers": customer_analysis,
                "insights": await self._generate_sales_insights(
                    daily_sales, category_performance, customer_analysis
                ),
            }

        except Exception as e:
            logger.error(f"판매 대시보드 생성 오류: {str(e)}")
            return {"error": str(e)}

    async def get_competition_dashboard(self) -> Dict[str, Any]:
        """
        경쟁 분석 대시보드

        Returns:
            경쟁 분석 대시보드
        """
        try:
            # 1. 주요 경쟁사 현황
            top_competitors = await self._get_top_competitors()

            # 2. 가격 경쟁력 분석
            price_competitiveness = await self._analyze_price_competitiveness()

            # 3. 경쟁사 전략 분석
            competitor_strategies = []
            for competitor in top_competitors[:5]:
                strategy = await self.competitor_monitor.analyze_competitor_strategy(
                    competitor["competitor_id"]
                )
                competitor_strategies.append(strategy)

            # 4. 시장 포지셔닝
            market_positioning = await self._analyze_market_positioning()

            # 5. 경쟁 위협 및 기회
            threats_opportunities = await self._analyze_competitive_threats()

            return {
                "top_competitors": top_competitors,
                "price_analysis": price_competitiveness,
                "strategies": competitor_strategies,
                "positioning": market_positioning,
                "threats_opportunities": threats_opportunities,
                "recommendations": await self._generate_competitive_recommendations(
                    price_competitiveness, market_positioning
                ),
            }

        except Exception as e:
            logger.error(f"경쟁 대시보드 생성 오류: {str(e)}")
            return {"error": str(e)}

    async def get_keyword_dashboard(self) -> Dict[str, Any]:
        """
        키워드 분석 대시보드

        Returns:
            키워드 분석 대시보드
        """
        try:
            # 1. 트렌딩 키워드
            trending_keywords = await self._get_trending_keywords()

            # 2. 기회 키워드
            opportunity_keywords = await self._get_opportunity_keywords()

            # 3. 키워드 성과
            keyword_performance = await self._analyze_keyword_performance()

            # 4. 키워드 조합 분석
            keyword_combinations = await self._analyze_keyword_combinations()

            # 5. 계절성 키워드
            seasonal_keywords = await self._identify_seasonal_keywords()

            return {
                "trending": trending_keywords,
                "opportunities": opportunity_keywords,
                "performance": keyword_performance,
                "combinations": keyword_combinations,
                "seasonal": seasonal_keywords,
                "insights": await self._generate_keyword_insights(
                    trending_keywords, opportunity_keywords
                ),
            }

        except Exception as e:
            logger.error(f"키워드 대시보드 생성 오류: {str(e)}")
            return {"error": str(e)}

    async def get_trend_dashboard(self) -> Dict[str, Any]:
        """
        트렌드 예측 대시보드

        Returns:
            트렌드 예측 대시보드
        """
        try:
            # 1. 시장 트렌드 예측
            market_predictions = await self.trend_predictor.predict_trends(horizon_days=30)

            # 2. 신흥 트렌드
            emerging_trends = await self.trend_predictor.identify_emerging_trends(
                min_growth_rate=50
            )

            # 3. 카테고리별 예측
            category_forecasts = await self._get_category_forecasts()

            # 4. 상품별 성과 예측
            product_forecasts = await self._get_product_forecasts()

            # 5. 리스크 분석
            risk_analysis = await self._analyze_trend_risks(market_predictions, emerging_trends)

            return {
                "market_trends": [
                    {
                        "trend": trend,
                        "opportunities": await self._extract_trend_opportunities(trend),
                    }
                    for trend in market_predictions[:10]
                ],
                "emerging": emerging_trends,
                "forecasts": {"categories": category_forecasts, "products": product_forecasts},
                "risks": risk_analysis,
                "action_items": await self._generate_trend_actions(
                    market_predictions, emerging_trends
                ),
            }

        except Exception as e:
            logger.error(f"트렌드 대시보드 생성 오류: {str(e)}")
            return {"error": str(e)}

    async def generate_report(
        self, report_type: str = "weekly", categories: Optional[List[str]] = None
    ) -> SourcingReport:
        """
        소싱 리포트 생성

        Args:
            report_type: 리포트 타입 (daily/weekly/monthly)
            categories: 대상 카테고리 (None이면 전체)

        Returns:
            소싱 리포트
        """
        try:
            # 기간 설정
            end_date = datetime.now()
            if report_type == "daily":
                start_date = end_date - timedelta(days=1)
            elif report_type == "weekly":
                start_date = end_date - timedelta(days=7)
            elif report_type == "monthly":
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(days=7)

            # 데이터 수집
            sales_data = await self._collect_sales_data_for_report(start_date, end_date, categories)

            market_trends = await self.trend_predictor.predict_trends(
                category=categories[0] if categories and len(categories) == 1 else None
            )

            opportunities = await self._collect_opportunities_for_report(categories)

            competitors = await self._collect_competitor_data_for_report(categories)

            keywords = await self._collect_keyword_data_for_report(categories)

            # 요약 및 분석
            summary = self._generate_report_summary(sales_data, market_trends, opportunities)

            key_findings = self._extract_key_findings(
                sales_data, market_trends, competitors, keywords
            )

            recommendations = self._generate_recommendations(
                sales_data, market_trends, opportunities, competitors
            )

            # 리포트 생성
            report = SourcingReport(
                report_id=f"REPORT_{report_type}_{datetime.now().strftime('%Y%m%d%H%M')}",
                report_type=report_type,
                title=f"{report_type.capitalize()} 소싱 인텔리전스 리포트",
                period_start=start_date,
                period_end=end_date,
                summary=summary,
                key_findings=key_findings,
                recommendations=recommendations,
                sales_metrics=sales_data.get("metrics"),
                market_trends=market_trends[:10],
                opportunities=opportunities[:20],
                competitors=competitors,
                keywords=keywords,
                created_at=datetime.now(),
            )

            # 리포트 저장
            await self._save_report(report)

            return report

        except Exception as e:
            logger.error(f"리포트 생성 오류: {str(e)}")
            raise

    async def export_dashboard_data(
        self, dashboard_type: str = "overview", format: str = "json"
    ) -> str:
        """
        대시보드 데이터 내보내기

        Args:
            dashboard_type: 대시보드 타입
            format: 출력 형식 (json/csv)

        Returns:
            내보낸 데이터
        """
        try:
            # 대시보드 데이터 가져오기
            if dashboard_type == "overview":
                data = await self.get_overview()
            elif dashboard_type == "sales":
                data = await self.get_sales_dashboard()
            elif dashboard_type == "competition":
                data = await self.get_competition_dashboard()
            elif dashboard_type == "keyword":
                data = await self.get_keyword_dashboard()
            elif dashboard_type == "trend":
                data = await self.get_trend_dashboard()
            else:
                raise ValueError(f"알 수 없는 대시보드 타입: {dashboard_type}")

            # 형식에 따라 변환
            if format == "json":
                return json.dumps(data, ensure_ascii=False, indent=2, default=str)
            elif format == "csv":
                return self._convert_to_csv(data)
            else:
                raise ValueError(f"지원하지 않는 형식: {format}")

        except Exception as e:
            logger.error(f"대시보드 내보내기 오류: {str(e)}")
            return ""

    def _is_cache_valid(self, cache_key: str) -> bool:
        """캐시 유효성 검사"""
        if cache_key not in self._dashboard_cache:
            return False

        cached = self._dashboard_cache[cache_key]
        age = (datetime.now() - cached["timestamp"]).seconds

        return age < self.refresh_interval

    async def _get_total_sales(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """전체 판매 데이터 조회"""
        orders = await self.storage.list(
            "orders",
            filters={
                "status": {"$in": ["delivered", "shipped"]},
                "order_date": {"$gte": start_date, "$lte": end_date},
            },
        )

        total_revenue = Decimal("0")
        total_quantity = 0
        category_sales = {}
        product_sales = {}

        for order in orders:
            for item in order.get("items", []):
                total_revenue += Decimal(str(item.get("total_price", 0)))
                total_quantity += item.get("quantity", 0)

                # 상품 정보
                product_id = item.get("product_id")
                if product_id:
                    product = await self.storage.get("products", product_id)
                    if product:
                        # 카테고리별 집계
                        category = product.get("category_name", "기타")
                        if category not in category_sales:
                            category_sales[category] = {"revenue": Decimal("0"), "quantity": 0}
                        category_sales[category]["revenue"] += Decimal(
                            str(item.get("total_price", 0))
                        )
                        category_sales[category]["quantity"] += item.get("quantity", 0)

                        # 상품별 집계
                        if product_id not in product_sales:
                            product_sales[product_id] = {
                                "name": product.get("name"),
                                "revenue": Decimal("0"),
                                "quantity": 0,
                            }
                        product_sales[product_id]["revenue"] += Decimal(
                            str(item.get("total_price", 0))
                        )
                        product_sales[product_id]["quantity"] += item.get("quantity", 0)

        # 정렬
        top_categories = sorted(
            [{"category": k, **v} for k, v in category_sales.items()],
            key=lambda x: x["revenue"],
            reverse=True,
        )

        top_products = sorted(
            [{"product_id": k, **v} for k, v in product_sales.items()],
            key=lambda x: x["revenue"],
            reverse=True,
        )

        return {
            "total_revenue": total_revenue,
            "total_quantity": total_quantity,
            "total_orders": len(orders),
            "average_order_value": total_revenue / len(orders) if orders else Decimal("0"),
            "top_categories": top_categories,
            "top_products": top_products,
        }

    def _calculate_growth_rate(self, current: Decimal, previous: Decimal) -> float:
        """성장률 계산"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0

        return float((current - previous) / previous * 100)

    def _determine_trend(self, growth_rate: float) -> TrendDirection:
        """트렌드 방향 결정"""
        if growth_rate > 10:
            return TrendDirection.UP
        elif growth_rate < -10:
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE

    async def _count_active_products(self) -> int:
        """활성 상품 수 계산"""
        products = await self.storage.list("products", filters={"status": "active"})
        return len(products)

    async def _count_tracked_competitors(self) -> int:
        """추적 중인 경쟁사 수 계산"""
        competitors = await self.storage.list("competitors")
        return len(set(c.get("competitor_id") for c in competitors))

    async def _get_top_opportunities(self) -> List[ProductOpportunity]:
        """주요 기회 조회"""
        # 최근 기회 조회
        opportunities = await self.storage.list(
            "product_opportunities",
            filters={"created_at": {"$gte": datetime.now() - timedelta(days=7)}},
        )

        # ProductOpportunity 객체로 변환
        opportunity_objects = []
        for opp_data in opportunities:
            try:
                opportunity = ProductOpportunity(**opp_data)
                opportunity_objects.append(opportunity)
            except:
                pass

        # 점수순 정렬
        opportunity_objects.sort(key=lambda x: x.opportunity_score, reverse=True)

        return opportunity_objects

    async def _get_competition_summary(self) -> Dict[str, Any]:
        """경쟁 현황 요약"""
        # 샘플 상품들의 경쟁 분석
        products = await self.storage.list("products", filters={"status": "active"}, limit=20)

        total_competitors = 0
        price_positions = []

        for product in products:
            competitors = await self.competitor_monitor.identify_competitors(product["id"])
            total_competitors += len(competitors)

            if competitors:
                price_analysis = await self.competitor_monitor.monitor_competitor_prices(
                    product["id"], competitors[:5]
                )

                if "position" in price_analysis:
                    price_positions.append(price_analysis["position"])

        # 평균 포지션
        if price_positions:
            avg_position = sum(p.get("percentile", 50) for p in price_positions) / len(
                price_positions
            )
        else:
            avg_position = 50

        return {
            "total_competitors": total_competitors,
            "average_price_position": avg_position,
            "competitiveness": (
                "high" if avg_position < 30 else "medium" if avg_position < 70 else "low"
            ),
        }

    async def _get_keyword_insights(self) -> Dict[str, Any]:
        """키워드 인사이트"""
        # 상위 카테고리의 키워드 분석
        categories = await self._get_top_categories(limit=5)

        rising_keywords = []
        opportunity_keywords = []

        for category in categories:
            # 기회 키워드
            opportunities = await self.keyword_researcher.find_opportunity_keywords(
                category, min_volume=1000, max_competition="medium"
            )

            for opp in opportunities[:3]:
                opportunity_keywords.append(
                    {
                        "keyword": opp["keyword"],
                        "category": category,
                        "score": opp["opportunity_score"],
                        "search_volume": opp["metrics"].search_volume,
                    }
                )

        # 정렬
        opportunity_keywords.sort(key=lambda x: x["score"], reverse=True)

        return {
            "total_tracked": len(opportunity_keywords),
            "rising": rising_keywords[:10],
            "opportunities": opportunity_keywords[:10],
        }

    async def _generate_alerts(
        self, sales_growth: float, market_trends: List[MarketTrend], competition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """알림 생성"""
        alerts = []

        # 판매 알림
        if sales_growth < -20:
            alerts.append(
                {
                    "type": "sales",
                    "level": "critical",
                    "message": "매출이 20% 이상 감소했습니다",
                    "action": "긴급 프로모션 검토 필요",
                }
            )
        elif sales_growth > 50:
            alerts.append(
                {
                    "type": "sales",
                    "level": "info",
                    "message": "매출이 50% 이상 증가했습니다",
                    "action": "재고 확충 검토",
                }
            )

        # 트렌드 알림
        for trend in market_trends[:3]:
            if trend.strength > 80 and trend.direction == TrendDirection.UP:
                alerts.append(
                    {
                        "type": "trend",
                        "level": "high",
                        "message": f"{trend.category} 카테고리 강한 상승 트렌드",
                        "action": "신규 상품 소싱 검토",
                    }
                )

        # 경쟁 알림
        if competition.get("average_price_position", 50) > 70:
            alerts.append(
                {
                    "type": "competition",
                    "level": "medium",
                    "message": "가격 경쟁력이 낮습니다",
                    "action": "가격 전략 재검토 필요",
                }
            )

        return alerts

    async def _get_top_categories(self, limit: int = 10) -> List[str]:
        """상위 카테고리 조회"""
        products = await self.storage.list("products")
        category_counts = {}

        for product in products:
            category = product.get("category_name", "기타")
            category_counts[category] = category_counts.get(category, 0) + 1

        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

        return [cat[0] for cat in sorted_categories[:limit]]

    async def _get_daily_sales_trend(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """일별 판매 추이"""
        daily_data = []
        current = start_date

        while current <= end_date:
            next_day = current + timedelta(days=1)

            day_sales = await self._get_total_sales(current, next_day)

            daily_data.append(
                {
                    "date": current,
                    "revenue": day_sales["total_revenue"],
                    "orders": day_sales["total_orders"],
                    "quantity": day_sales["total_quantity"],
                }
            )

            current = next_day

        return daily_data

    async def _get_category_performance(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """카테고리별 성과"""
        categories = await self._get_top_categories()
        performances = []

        for category in categories[:10]:
            metrics = await self.sales_analyzer.analyze_category_sales(
                category, start_date, end_date
            )

            if metrics:
                performances.append(
                    {
                        "category": category,
                        "revenue": metrics.get("total_revenue", 0),
                        "sales": metrics.get("total_sales", 0),
                        "products": len(metrics.get("product_metrics", [])),
                    }
                )

        return performances

    async def _get_product_performance(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """상품별 성과"""
        # 상위 상품 조회
        sales_data = await self._get_total_sales(start_date, end_date)
        top_products = sales_data["top_products"][:20]

        performances = []
        for product_data in top_products:
            product_id = product_data["product_id"]
            product = await self.storage.get("products", product_id)

            if product:
                metrics = await self.sales_analyzer.analyze_product_sales(
                    product_id, start_date, end_date
                )

                performances.append(
                    {
                        "product_id": product_id,
                        "name": product.get("name"),
                        "category": product.get("category_name"),
                        "revenue": metrics.total_revenue,
                        "sales": metrics.total_sales,
                        "growth_rate": metrics.growth_rate,
                        "trend": metrics.trend,
                    }
                )

        return performances

    async def _analyze_hourly_pattern(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[int, Dict[str, Any]]:
        """시간대별 패턴 분석"""
        hourly_data = {hour: {"orders": 0, "revenue": Decimal("0")} for hour in range(24)}

        orders = await self.storage.list(
            "orders", filters={"order_date": {"$gte": start_date, "$lte": end_date}}
        )

        for order in orders:
            order_date = order.get("order_date")
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date)

            hour = order_date.hour
            hourly_data[hour]["orders"] += 1

            for item in order.get("items", []):
                hourly_data[hour]["revenue"] += Decimal(str(item.get("total_price", 0)))

        return hourly_data

    async def _analyze_weekday_pattern(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[int, Dict[str, Any]]:
        """요일별 패턴 분석"""
        weekday_data = {day: {"orders": 0, "revenue": Decimal("0")} for day in range(7)}

        orders = await self.storage.list(
            "orders", filters={"order_date": {"$gte": start_date, "$lte": end_date}}
        )

        for order in orders:
            order_date = order.get("order_date")
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date)

            weekday = order_date.weekday()
            weekday_data[weekday]["orders"] += 1

            for item in order.get("items", []):
                weekday_data[weekday]["revenue"] += Decimal(str(item.get("total_price", 0)))

        return weekday_data

    async def _analyze_customers(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """고객 분석"""
        orders = await self.storage.list(
            "orders", filters={"order_date": {"$gte": start_date, "$lte": end_date}}
        )

        customer_orders = {}
        total_revenue = Decimal("0")

        for order in orders:
            customer_id = order.get("customer", {}).get("phone", "unknown")

            if customer_id not in customer_orders:
                customer_orders[customer_id] = {"orders": 0, "revenue": Decimal("0")}

            customer_orders[customer_id]["orders"] += 1

            for item in order.get("items", []):
                revenue = Decimal(str(item.get("total_price", 0)))
                customer_orders[customer_id]["revenue"] += revenue
                total_revenue += revenue

        # 분석
        total_customers = len(customer_orders)
        repeat_customers = sum(1 for c in customer_orders.values() if c["orders"] > 1)

        # 파레토 분석 (상위 20% 고객)
        sorted_customers = sorted(
            customer_orders.values(), key=lambda x: x["revenue"], reverse=True
        )

        top_20_percent = int(total_customers * 0.2)
        top_customers_revenue = sum(c["revenue"] for c in sorted_customers[:top_20_percent])

        return {
            "total_customers": total_customers,
            "repeat_rate": (repeat_customers / total_customers * 100) if total_customers > 0 else 0,
            "average_order_value": total_revenue / len(orders) if orders else Decimal("0"),
            "pareto_ratio": (
                float(top_customers_revenue / total_revenue * 100) if total_revenue > 0 else 0
            ),
        }

    async def _generate_sales_insights(
        self,
        daily_sales: List[Dict[str, Any]],
        category_performance: List[Dict[str, Any]],
        customer_analysis: Dict[str, Any],
    ) -> List[str]:
        """판매 인사이트 생성"""
        insights = []

        # 매출 트렌드
        if daily_sales:
            recent_revenue = sum(d["revenue"] for d in daily_sales[-7:])
            previous_revenue = sum(d["revenue"] for d in daily_sales[-14:-7])

            if previous_revenue > 0:
                weekly_growth = (recent_revenue - previous_revenue) / previous_revenue * 100

                if weekly_growth > 20:
                    insights.append(f"최근 일주일 매출이 {weekly_growth:.1f}% 증가했습니다")
                elif weekly_growth < -20:
                    insights.append(f"최근 일주일 매출이 {abs(weekly_growth):.1f}% 감소했습니다")

        # 카테고리 집중도
        if category_performance:
            top_category_revenue = category_performance[0]["revenue"]
            total_revenue = sum(c["revenue"] for c in category_performance)

            if total_revenue > 0:
                concentration = top_category_revenue / total_revenue * 100

                if concentration > 50:
                    insights.append(
                        f"{category_performance[0]['category']} 카테고리가 "
                        f"전체 매출의 {concentration:.1f}%를 차지합니다"
                    )

        # 고객 인사이트
        if customer_analysis["pareto_ratio"] > 80:
            insights.append(
                f"상위 20% 고객이 전체 매출의 {customer_analysis['pareto_ratio']:.1f}%를 "
                "차지합니다 - VIP 관리 강화 필요"
            )

        if customer_analysis["repeat_rate"] < 20:
            insights.append(
                f"재구매율이 {customer_analysis['repeat_rate']:.1f}%로 낮습니다 - "
                "고객 만족도 개선 필요"
            )

        return insights

    async def _get_top_competitors(self) -> List[Dict[str, Any]]:
        """주요 경쟁사 조회"""
        # 모든 경쟁사 정보 수집
        competitor_stats = {}

        products = await self.storage.list("products", filters={"status": "active"}, limit=50)

        for product in products:
            competitors = await self.competitor_monitor.identify_competitors(product["id"])

            for comp in competitors:
                comp_id = comp.competitor_id

                if comp_id not in competitor_stats:
                    competitor_stats[comp_id] = {
                        "competitor_id": comp_id,
                        "name": comp.name,
                        "marketplace": comp.marketplace,
                        "product_count": 0,
                        "avg_rating": [],
                        "total_reviews": 0,
                    }

                competitor_stats[comp_id]["product_count"] += 1
                if comp.average_rating:
                    competitor_stats[comp_id]["avg_rating"].append(comp.average_rating)
                if comp.review_count:
                    competitor_stats[comp_id]["total_reviews"] += comp.review_count

        # 평균 계산 및 정렬
        top_competitors = []
        for comp_id, stats in competitor_stats.items():
            if stats["avg_rating"]:
                avg_rating = sum(stats["avg_rating"]) / len(stats["avg_rating"])
            else:
                avg_rating = 0

            top_competitors.append(
                {
                    "competitor_id": comp_id,
                    "name": stats["name"],
                    "marketplace": stats["marketplace"],
                    "competing_products": stats["product_count"],
                    "average_rating": avg_rating,
                    "total_reviews": stats["total_reviews"],
                }
            )

        # 경쟁 상품 수로 정렬
        top_competitors.sort(key=lambda x: x["competing_products"], reverse=True)

        return top_competitors[:20]

    async def _analyze_price_competitiveness(self) -> Dict[str, Any]:
        """가격 경쟁력 분석"""
        products = await self.storage.list("products", filters={"status": "active"}, limit=50)

        price_positions = []
        competitive_products = 0
        expensive_products = 0

        for product in products:
            competitors = await self.competitor_monitor.identify_competitors(product["id"])

            if competitors:
                price_analysis = await self.competitor_monitor.monitor_competitor_prices(
                    product["id"], competitors[:10]
                )

                if "position" in price_analysis:
                    position = price_analysis["position"]
                    price_positions.append(position["percentile"])

                    if position["competitiveness"] == "very_competitive":
                        competitive_products += 1
                    elif position["competitiveness"] == "expensive":
                        expensive_products += 1

        # 분석
        if price_positions:
            avg_position = sum(price_positions) / len(price_positions)
        else:
            avg_position = 50

        return {
            "average_position": avg_position,
            "competitive_products": competitive_products,
            "expensive_products": expensive_products,
            "total_analyzed": len(price_positions),
            "recommendation": self._get_price_recommendation(
                avg_position, competitive_products, expensive_products
            ),
        }

    def _get_price_recommendation(
        self, avg_position: float, competitive: int, expensive: int
    ) -> str:
        """가격 추천사항"""
        if avg_position < 30:
            return "전반적으로 가격 경쟁력이 우수합니다"
        elif avg_position > 70:
            return "가격 경쟁력 개선이 필요합니다"
        elif expensive > competitive:
            return "일부 상품의 가격 조정을 검토하세요"
        else:
            return "적절한 가격 포지셔닝을 유지하고 있습니다"

    async def _analyze_market_positioning(self) -> Dict[str, Any]:
        """시장 포지셔닝 분석"""
        # 카테고리별 시장 점유율 추정
        categories = await self._get_top_categories(limit=5)
        positioning = []

        for category in categories:
            # 카테고리 판매 분석
            our_sales = await self.sales_analyzer.analyze_category_sales(
                category, datetime.now() - timedelta(days=30), datetime.now()
            )

            # 시장 규모 추정 (실제로는 외부 데이터 필요)
            estimated_market_size = our_sales.get("total_sales", 0) * 20  # 5% 점유율 가정

            positioning.append(
                {
                    "category": category,
                    "our_sales": our_sales.get("total_sales", 0),
                    "market_share": 5.0,  # 추정치
                    "position": "challenger",  # leader/challenger/follower/nicher
                }
            )

        return {
            "by_category": positioning,
            "overall_position": "challenger",
            "strengths": ["가격 경쟁력", "빠른 배송"],
            "weaknesses": ["브랜드 인지도", "상품 다양성"],
        }

    async def _analyze_competitive_threats(self) -> Dict[str, Any]:
        """경쟁 위협 분석"""
        # 신규 진입자
        new_competitors = await self.competitor_monitor.track_new_competitors(
            category=None, marketplace=None  # 전체
        )

        # 가격 전쟁 위험
        price_war_risk = await self._assess_price_war_risk()

        # 대체품 위협
        substitution_threats = await self._assess_substitution_threats()

        return {
            "new_entrants": {
                "count": len(new_competitors),
                "threat_level": "high" if len(new_competitors) > 5 else "medium",
            },
            "price_war": price_war_risk,
            "substitution": substitution_threats,
            "opportunities": ["차별화된 상품 개발", "니치 시장 공략", "번들 상품 전략"],
        }

    async def _assess_price_war_risk(self) -> Dict[str, Any]:
        """가격 전쟁 위험 평가"""
        # 최근 가격 변동 추적
        recent_changes = await self.storage.list(
            "competitor_price_history",
            filters={"recorded_at": {"$gte": datetime.now() - timedelta(days=7)}},
        )

        price_drops = sum(
            1 for c in recent_changes if c.get("price", 0) < c.get("previous_price", 0)
        )

        if price_drops > len(recent_changes) * 0.3:
            risk_level = "high"
        elif price_drops > len(recent_changes) * 0.1:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "price_drops": price_drops,
            "total_changes": len(recent_changes),
        }

    async def _assess_substitution_threats(self) -> Dict[str, Any]:
        """대체품 위협 평가"""
        # 카테고리별 신상품 출시 추적
        new_products = await self.storage.list(
            "products", filters={"created_at": {"$gte": datetime.now() - timedelta(days=30)}}
        )

        return {
            "new_products": len(new_products),
            "threat_level": "high" if len(new_products) > 100 else "medium",
        }

    async def _generate_competitive_recommendations(
        self, price_analysis: Dict[str, Any], positioning: Dict[str, Any]
    ) -> List[str]:
        """경쟁 전략 추천"""
        recommendations = []

        # 가격 전략
        if price_analysis["average_position"] > 70:
            recommendations.append("가격 경쟁력 강화를 위한 원가 절감 방안 모색")
        elif price_analysis["average_position"] < 30:
            recommendations.append("프리미엄 라인 추가로 수익성 개선 검토")

        # 포지셔닝 전략
        if positioning["overall_position"] == "challenger":
            recommendations.append("차별화된 가치 제안으로 시장 점유율 확대")

        # 약점 보완
        for weakness in positioning.get("weaknesses", []):
            if weakness == "브랜드 인지도":
                recommendations.append("소셜 미디어 마케팅 강화로 브랜드 인지도 향상")
            elif weakness == "상품 다양성":
                recommendations.append("인기 카테고리 중심으로 상품 라인업 확대")

        return recommendations[:5]

    async def _get_trending_keywords(self) -> List[Dict[str, Any]]:
        """트렌딩 키워드 조회"""
        # 모든 카테고리의 키워드 트렌드
        trending = []
        categories = await self._get_top_categories(limit=5)

        for category in categories:
            # 카테고리별 키워드 추출
            products = await self.storage.list(
                "products", filters={"category_name": category}, limit=20
            )

            keywords = []
            for product in products:
                name_words = product.get("name", "").split()
                keywords.extend(name_words[:3])

            # 키워드 빈도
            keyword_counts = {}
            for kw in keywords:
                if len(kw) > 2:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

            # 상위 키워드의 트렌드 조회
            for keyword, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]:
                trends = await self.keyword_researcher.track_keyword_trends([keyword], days=30)

                trend_data = trends.get("keyword_trends", {}).get(keyword, {})
                if trend_data.get("trend") == TrendDirection.UP:
                    trending.append(
                        {
                            "keyword": keyword,
                            "category": category,
                            "trend": trend_data.get("trend"),
                            "strength": trend_data.get("trend_strength", 0),
                            "current_volume": trend_data.get("current_volume", 0),
                        }
                    )

        # 정렬
        trending.sort(key=lambda x: x["strength"], reverse=True)
        return trending[:20]

    async def _get_opportunity_keywords(self) -> List[Dict[str, Any]]:
        """기회 키워드 조회"""
        opportunities = []
        categories = await self._get_top_categories(limit=5)

        for category in categories:
            # 카테고리별 기회 키워드
            keyword_opps = await self.keyword_researcher.find_opportunity_keywords(
                category, min_volume=1000, max_competition="medium"
            )

            for opp in keyword_opps[:5]:
                opportunities.append(
                    {
                        "keyword": opp["keyword"],
                        "category": category,
                        "opportunity_score": opp["opportunity_score"],
                        "search_volume": opp["metrics"].search_volume,
                        "competition": opp["metrics"].competition_level,
                        "potential_revenue": float(opp.get("potential_revenue", 0)),
                    }
                )

        # 점수순 정렬
        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

        return opportunities[:20]

    async def _analyze_keyword_performance(self) -> Dict[str, Any]:
        """키워드 성과 분석"""
        # 키워드별 상품 매칭 및 성과
        keyword_performance = {}

        # 상위 상품의 키워드 분석
        top_products = await self.storage.list("products", filters={"status": "active"}, limit=50)

        for product in top_products:
            # 상품 키워드 추출
            keywords = product.get("name", "").split()[:3]

            # 상품 성과
            metrics = await self.sales_analyzer.analyze_product_sales(
                product["id"], datetime.now() - timedelta(days=30), datetime.now()
            )

            for keyword in keywords:
                if len(keyword) > 2:
                    if keyword not in keyword_performance:
                        keyword_performance[keyword] = {
                            "products": 0,
                            "total_sales": 0,
                            "total_revenue": Decimal("0"),
                        }

                    keyword_performance[keyword]["products"] += 1
                    keyword_performance[keyword]["total_sales"] += metrics.total_sales
                    keyword_performance[keyword]["total_revenue"] += metrics.total_revenue

        # 상위 성과 키워드
        top_performers = sorted(
            [{"keyword": k, **v} for k, v in keyword_performance.items()],
            key=lambda x: x["total_revenue"],
            reverse=True,
        )[:20]

        return {"top_performers": top_performers, "total_keywords": len(keyword_performance)}

    async def _analyze_keyword_combinations(self) -> List[Dict[str, Any]]:
        """키워드 조합 분석"""
        # 상위 키워드 조합
        base_keywords = ["무선", "휴대용", "미니", "스마트", "LED", "충전식"]

        combinations = await self.keyword_researcher.analyze_keyword_combinations(base_keywords)

        return combinations[:10]

    async def _identify_seasonal_keywords(self) -> List[Dict[str, Any]]:
        """계절성 키워드 식별"""
        seasonal_keywords = []

        # 계절별 키워드 (실제로는 과거 데이터 분석 필요)
        current_month = datetime.now().month

        if current_month in [12, 1, 2]:  # 겨울
            seasonal_keywords.extend(
                [
                    {"keyword": "히터", "season": "winter", "strength": 90},
                    {"keyword": "가습기", "season": "winter", "strength": 85},
                    {"keyword": "전기장판", "season": "winter", "strength": 80},
                ]
            )
        elif current_month in [6, 7, 8]:  # 여름
            seasonal_keywords.extend(
                [
                    {"keyword": "선풍기", "season": "summer", "strength": 90},
                    {"keyword": "에어컨", "season": "summer", "strength": 85},
                    {"keyword": "제습기", "season": "summer", "strength": 80},
                ]
            )

        return seasonal_keywords

    async def _generate_keyword_insights(
        self, trending: List[Dict[str, Any]], opportunities: List[Dict[str, Any]]
    ) -> List[str]:
        """키워드 인사이트 생성"""
        insights = []

        # 트렌딩 인사이트
        if trending:
            top_trending = trending[0]
            insights.append(
                f"'{top_trending['keyword']}' 키워드가 "
                f"{top_trending['strength']:.0f}% 상승 중입니다"
            )

        # 기회 인사이트
        if opportunities:
            low_comp_opps = [o for o in opportunities if o["competition"] == "low"]
            if low_comp_opps:
                insights.append(f"{len(low_comp_opps)}개의 저경쟁 고검색량 키워드를 발견했습니다")

        # 수익 잠재력
        total_potential = sum(o.get("potential_revenue", 0) for o in opportunities[:10])
        if total_potential > 10000000:
            insights.append(f"상위 10개 기회 키워드의 월 수익 잠재력: " f"{total_potential:,.0f}원")

        return insights

    async def _get_category_forecasts(self) -> List[Dict[str, Any]]:
        """카테고리별 예측"""
        forecasts = []
        categories = await self._get_top_categories(limit=5)

        for category in categories:
            # 카테고리 트렌드 예측
            trends = await self.trend_predictor.predict_trends(category=category, horizon_days=30)

            if trends:
                trend = trends[0]
                forecasts.append(
                    {
                        "category": category,
                        "forecast_direction": trend.forecast_direction,
                        "confidence": trend.confidence_level,
                        "opportunities": len(
                            [p for p in trend.trending_products if p.get("score", 0) > 70]
                        ),
                    }
                )

        return forecasts

    async def _get_product_forecasts(self) -> List[Dict[str, Any]]:
        """상품별 예측"""
        forecasts = []

        # 상위 상품 예측
        top_products = await self.storage.list("products", filters={"status": "active"}, limit=10)

        for product in top_products:
            forecast = await self.trend_predictor.predict_product_performance(
                product["id"], horizon_days=30
            )

            if "error" not in forecast:
                forecasts.append(
                    {
                        "product_id": product["id"],
                        "name": product["name"],
                        "forecast": forecast["forecast"],
                        "confidence": forecast["confidence"],
                        "risks": forecast.get("risks", []),
                    }
                )

        return forecasts

    async def _analyze_trend_risks(
        self, market_predictions: List[MarketTrend], emerging_trends: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """트렌드 리스크 분석"""
        risks = []

        # 과열 리스크
        for trend in market_predictions:
            if trend.strength > 90 and trend.momentum > 80:
                risks.append(
                    {
                        "type": "overheating",
                        "category": trend.category,
                        "level": "high",
                        "description": f"{trend.category} 시장 과열 가능성",
                        "mitigation": "단계적 진입 및 재고 관리 강화",
                    }
                )

        # 급성장 리스크
        for emerging in emerging_trends:
            if emerging["growth_rate"] > 200:
                risks.append(
                    {
                        "type": "bubble",
                        "name": emerging["name"],
                        "level": "medium",
                        "description": "과도한 성장률 - 거품 가능성",
                        "mitigation": "보수적 접근 및 시장 모니터링",
                    }
                )

        return risks

    async def _extract_trend_opportunities(self, trend: MarketTrend) -> List[Dict[str, Any]]:
        """트렌드별 기회 추출"""
        opportunities = []

        # 키워드 기반 기회
        for keyword in trend.trending_keywords[:5]:
            metrics = await self.keyword_researcher.research_keyword(keyword, trend.category)

            if metrics.competition_level in ["low", "medium"]:
                opportunities.append(
                    {
                        "type": "keyword",
                        "name": keyword,
                        "search_volume": metrics.search_volume,
                        "competition": metrics.competition_level,
                    }
                )

        return opportunities

    async def _generate_trend_actions(
        self, predictions: List[MarketTrend], emerging: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """트렌드 기반 액션 아이템"""
        actions = []

        # 상승 트렌드 액션
        for trend in predictions:
            if trend.direction == TrendDirection.UP and trend.confidence_level > 70:
                actions.append(
                    {
                        "priority": "high",
                        "action": f"{trend.category} 카테고리 상품 확대",
                        "reason": f"강한 상승 트렌드 (신뢰도 {trend.confidence_level:.0f}%)",
                        "timeline": "즉시",
                    }
                )

        # 신흥 트렌드 액션
        for em in emerging[:3]:
            if em["risk_level"] == "low":
                actions.append(
                    {
                        "priority": "medium",
                        "action": f"'{em['name']}' 관련 상품 테스트",
                        "reason": f"{em['growth_rate']:.0f}% 성장률",
                        "timeline": "1주일 내",
                    }
                )

        return actions

    async def _collect_sales_data_for_report(
        self, start_date: datetime, end_date: datetime, categories: Optional[List[str]]
    ) -> Dict[str, Any]:
        """리포트용 판매 데이터 수집"""
        if categories:
            # 특정 카테고리
            total_sales = 0
            total_revenue = Decimal("0")

            for category in categories:
                cat_sales = await self.sales_analyzer.analyze_category_sales(
                    category, start_date, end_date
                )
                total_sales += cat_sales.get("total_sales", 0)
                total_revenue += cat_sales.get("total_revenue", Decimal("0"))

            # 이전 기간
            prev_start = start_date - (end_date - start_date)
            prev_end = start_date

            prev_sales = 0
            prev_revenue = Decimal("0")

            for category in categories:
                cat_sales = await self.sales_analyzer.analyze_category_sales(
                    category, prev_start, prev_end
                )
                prev_sales += cat_sales.get("total_sales", 0)
                prev_revenue += cat_sales.get("total_revenue", Decimal("0"))

            growth_rate = self._calculate_growth_rate(total_revenue, prev_revenue)

            metrics = SalesMetrics(
                total_sales=total_sales,
                total_revenue=total_revenue,
                average_price=total_revenue / total_sales if total_sales > 0 else Decimal("0"),
                growth_rate=growth_rate,
                trend=self._determine_trend(growth_rate),
                period_start=start_date,
                period_end=end_date,
            )

            return {"metrics": metrics}
        else:
            # 전체
            sales_data = await self._get_total_sales(start_date, end_date)
            prev_data = await self._get_total_sales(
                start_date - (end_date - start_date), start_date
            )

            growth_rate = self._calculate_growth_rate(
                sales_data["total_revenue"], prev_data["total_revenue"]
            )

            metrics = SalesMetrics(
                total_sales=sales_data["total_quantity"],
                total_revenue=sales_data["total_revenue"],
                average_price=sales_data["average_order_value"],
                growth_rate=growth_rate,
                trend=self._determine_trend(growth_rate),
                period_start=start_date,
                period_end=end_date,
            )

            return {"metrics": metrics}

    async def _collect_opportunities_for_report(
        self, categories: Optional[List[str]]
    ) -> List[ProductOpportunity]:
        """리포트용 기회 수집"""
        if categories:
            # 특정 카테고리
            all_opportunities = []

            for category in categories:
                trends = await self.trend_predictor.predict_trends(
                    category=category, horizon_days=30
                )

                for trend in trends:
                    # 트렌드에서 기회 추출 (실제로는 기회 데이터 포함)
                    pass

            return all_opportunities
        else:
            return await self._get_top_opportunities()

    async def _collect_competitor_data_for_report(
        self, categories: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """리포트용 경쟁사 데이터 수집"""
        competitors = await self._get_top_competitors()

        if categories:
            # 카테고리 필터링
            filtered = []
            for comp in competitors:
                # 실제로는 경쟁사의 카테고리 확인 필요
                filtered.append(comp)
            return filtered[:10]

        return competitors[:10]

    async def _collect_keyword_data_for_report(
        self, categories: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """리포트용 키워드 데이터 수집"""
        if categories:
            keywords = []
            for category in categories:
                cat_keywords = await self.keyword_researcher.find_opportunity_keywords(
                    category, min_volume=1000
                )

                for kw in cat_keywords[:10]:
                    keywords.append(
                        {"keyword": kw["keyword"], "category": category, "metrics": kw["metrics"]}
                    )

            return keywords
        else:
            return await self._get_opportunity_keywords()

    def _generate_report_summary(
        self,
        sales_data: Dict[str, Any],
        trends: List[MarketTrend],
        opportunities: List[ProductOpportunity],
    ) -> str:
        """리포트 요약 생성"""
        metrics = sales_data.get("metrics")

        summary_parts = []

        # 판매 요약
        if metrics:
            summary_parts.append(
                f"분석 기간 동안 총 {metrics.total_sales:,}개 상품이 판매되어 "
                f"{metrics.total_revenue:,.0f}원의 매출을 기록했습니다. "
                f"전 기간 대비 {metrics.growth_rate:+.1f}% {'성장' if metrics.growth_rate > 0 else '하락'}했습니다."
            )

        # 트렌드 요약
        if trends:
            up_trends = [t for t in trends if t.direction == TrendDirection.UP]
            if up_trends:
                summary_parts.append(
                    f"{len(up_trends)}개의 상승 트렌드가 감지되었으며, "
                    f"특히 {up_trends[0].category} 카테고리가 주목받고 있습니다."
                )

        # 기회 요약
        if opportunities:
            high_score_opps = [o for o in opportunities if o.opportunity_score > 80]
            if high_score_opps:
                summary_parts.append(
                    f"{len(high_score_opps)}개의 고득점 사업 기회가 발견되었습니다."
                )

        return " ".join(summary_parts)

    def _extract_key_findings(
        self,
        sales_data: Dict[str, Any],
        trends: List[MarketTrend],
        competitors: List[Dict[str, Any]],
        keywords: List[Dict[str, Any]],
    ) -> List[str]:
        """주요 발견사항 추출"""
        findings = []

        # 판매 관련
        metrics = sales_data.get("metrics")
        if metrics and metrics.growth_rate > 30:
            findings.append(f"매출이 {metrics.growth_rate:.1f}% 급성장했습니다")

        # 트렌드 관련
        strong_trends = [t for t in trends if t.strength > 80]
        if strong_trends:
            findings.append(
                f"{len(strong_trends)}개 카테고리에서 강한 성장 트렌드가 확인되었습니다"
            )

        # 경쟁 관련
        if competitors:
            avg_reviews = sum(c.get("total_reviews", 0) for c in competitors[:5]) / 5
            if avg_reviews > 1000:
                findings.append("주요 경쟁사들의 고객 리뷰가 매우 활발합니다")

        # 키워드 관련
        low_comp_keywords = [
            k for k in keywords if k.get("metrics", {}).get("competition_level") == "low"
        ]
        if len(low_comp_keywords) > 5:
            findings.append(f"{len(low_comp_keywords)}개의 저경쟁 키워드 기회가 있습니다")

        return findings

    def _generate_recommendations(
        self,
        sales_data: Dict[str, Any],
        trends: List[MarketTrend],
        opportunities: List[ProductOpportunity],
        competitors: List[Dict[str, Any]],
    ) -> List[str]:
        """추천사항 생성"""
        recommendations = []

        # 성장 전략
        metrics = sales_data.get("metrics")
        if metrics and metrics.trend == TrendDirection.UP:
            recommendations.append("현재의 성장 모멘텀을 활용하여 인기 카테고리 상품을 확대하세요")
        elif metrics and metrics.trend == TrendDirection.DOWN:
            recommendations.append("매출 하락 원인을 분석하고 프로모션 전략을 재검토하세요")

        # 트렌드 활용
        if trends:
            up_trend_categories = [
                t.category
                for t in trends
                if t.direction == TrendDirection.UP and t.confidence_level > 70
            ][:3]

            if up_trend_categories:
                recommendations.append(
                    f"{', '.join(up_trend_categories)} 카테고리에 집중 투자하세요"
                )

        # 기회 활용
        if opportunities:
            low_barrier_opps = [
                o for o in opportunities if o.entry_barrier == "low" and o.opportunity_score > 70
            ]

            if low_barrier_opps:
                recommendations.append(
                    f"진입 장벽이 낮은 {len(low_barrier_opps)}개 기회를 " "우선적으로 검토하세요"
                )

        # 경쟁 대응
        if competitors and len(competitors) > 10:
            recommendations.append("경쟁이 치열한 시장에서 차별화 전략을 강화하세요")

        return recommendations[:10]

    async def _save_report(self, report: SourcingReport):
        """리포트 저장"""
        report_data = report.dict()
        report_data["created_at"] = report.created_at

        await self.storage.create("sourcing_reports", report_data)

        # 오래된 리포트 정리
        cutoff_date = datetime.now() - timedelta(days=self.report_retention_days)
        old_reports = await self.storage.list(
            "sourcing_reports", filters={"created_at": {"$lt": cutoff_date}}
        )

        for old_report in old_reports:
            await self.storage.delete("sourcing_reports", old_report["id"])

    def _convert_to_csv(self, data: Dict[str, Any]) -> str:
        """CSV 변환"""
        # 간단한 CSV 변환 (실제로는 pandas 등 사용)
        lines = []

        # 헤더
        if "summary" in data:
            lines.append("지표,값")
            for key, value in data["summary"].items():
                lines.append(f"{key},{value}")

        return "\n".join(lines)
