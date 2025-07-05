"""
소싱 매니저
판매 분석, 경쟁사 모니터링, 키워드 연구를 통합 관리
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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
from dropshipping.storage.base import BaseStorage


class SourcingManager:
    """소싱 통합 관리자"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 관리자 설정
        """
        self.storage = storage
        self.config = config or {}

        # 컴포넌트 초기화
        self.sales_analyzer = SalesAnalyzer(storage, self.config.get("sales", {}))
        self.competitor_monitor = CompetitorMonitor(storage, self.config.get("competitor", {}))
        self.keyword_researcher = KeywordResearcher(storage, self.config.get("keyword", {}))

        # 설정
        self.opportunity_threshold = self.config.get(
            "opportunity_threshold", 70
        )  # 기회 점수 임계값
        self.report_retention_days = self.config.get("report_retention_days", 90)

    async def find_product_opportunities(
        self, categories: Optional[List[str]] = None, min_score: float = 70.0
    ) -> List[ProductOpportunity]:
        """
        상품 기회 발굴

        Args:
            categories: 분석할 카테고리 목록
            min_score: 최소 기회 점수

        Returns:
            상품 기회 목록
        """
        opportunities = []

        try:
            # 카테고리 목록
            if not categories:
                categories = await self._get_active_categories()

            # 모든 카테고리에 대한 트렌드 미리 분석
            trends = await self.sales_analyzer.detect_trends(lookback_days=30)
            trends_by_category = {t.category: t for t in trends}

            tasks = []
            for category in categories:
                tasks.append(
                    self._find_opportunities_for_category(
                        category, trends_by_category.get(category), min_score
                    )
                )

            results = await asyncio.gather(*tasks)
            opportunities = [opp for res in results for opp in res]  # Flatten list

            # 점수순 정렬
            opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)

            # DB 저장
            if opportunities:
                await asyncio.gather(*[self._save_opportunity(opp) for opp in opportunities])

            return opportunities

        except Exception as e:
            logger.error(f"상품 기회 발굴 오류: {str(e)}")
            return opportunities

    async def _find_opportunities_for_category(
        self, category: str, category_trend: Optional[MarketTrend], min_score: float
    ) -> List[ProductOpportunity]:
        """특정 카테고리의 상품 기회를 찾습니다."""

        opportunities = []
        logger.info(f"{category} 카테고리 기회 분석 시작")

        if not category_trend or category_trend.strength < 30:
            return []

        opportunity_keywords = await self.keyword_researcher.find_opportunity_keywords(
            category, min_volume=500, max_competition="medium"
        )

        for keyword_data in opportunity_keywords[:10]:  # 상위 10개
            keyword = keyword_data["keyword"]
            metrics = keyword_data["metrics"]

            # 병렬 분석 실행
            competition_analysis, profitability, supplier_analysis = await asyncio.gather(
                self._analyze_keyword_competition(keyword, category),
                self._analyze_profitability(
                    keyword, metrics, await self._analyze_keyword_competition(keyword, category)
                ),
                self._analyze_suppliers(keyword, category),
            )

            opportunity_score = self._calculate_opportunity_score(
                keyword_data, competition_analysis, profitability, supplier_analysis, category_trend
            )

            if opportunity_score >= min_score:
                risks = self._analyze_risks(competition_analysis, supplier_analysis, category_trend)

                opportunity = ProductOpportunity(
                    opportunity_id=f"OPP_{category}_{keyword}_{datetime.now().strftime('%Y%m%d')}",
                    opportunity_score=opportunity_score,
                    product_name=f"{keyword} 상품",
                    category=category,
                    keywords=[keyword] + metrics.related_keywords[:5],
                    market_demand=self._classify_demand(metrics.search_volume),
                    competition_level=metrics.competition_level,
                    entry_barrier=self._assess_entry_barrier(competition_analysis),
                    estimated_price=profitability["recommended_price"],
                    estimated_cost=profitability["estimated_cost"],
                    estimated_margin=profitability["estimated_margin"],
                    estimated_monthly_sales=profitability["estimated_sales"],
                    supplier_count=supplier_analysis["count"],
                    recommended_suppliers=supplier_analysis["recommended"][:3],
                    risks=risks,
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=30),
                )
                opportunities.append(opportunity)

        return opportunities

    async def generate_sourcing_report(
        self, report_type: str = "weekly", categories: Optional[List[str]] = None
    ) -> SourcingReport:
        """
        소싱 리포트 생성

        Args:
            report_type: 리포트 타입 (daily/weekly/monthly)
            categories: 분석할 카테고리

        Returns:
            소싱 리포트
        """
        try:
            # 기간 설정
            period_map = {"daily": 1, "weekly": 7, "monthly": 30}
            days = period_map.get(report_type, 7)

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 카테고리 목록
            if not categories:
                categories = await self._get_active_categories()

            # 1. 판매 분석
            sales_metrics = await self._generate_sales_summary(categories, start_date, end_date)

            # 2. 시장 트렌드
            all_market_trends = await self.sales_analyzer.detect_trends(lookback_days=days)
            # overall_trend가 None이면 제외
            market_trends = [t for t in all_market_trends if t is not None][:5]
            opportunities = await self.find_product_opportunities(
                categories, min_score=self.opportunity_threshold
            )

            # 4. 경쟁사 동향
            competitor_updates = await self._get_competitor_updates(categories, start_date)

            # 5. 키워드 인사이트
            keyword_insights = await self._generate_keyword_insights(categories, days)

            # 주요 발견사항
            key_findings = self._extract_key_findings(
                sales_metrics, market_trends, opportunities, competitor_updates, keyword_insights
            )

            # 추천사항
            recommendations = self._generate_recommendations(
                key_findings, opportunities, market_trends
            )

            # 리포트 생성
            report = SourcingReport(
                report_id=f"REPORT_{report_type}_{datetime.now().strftime('%Y%m%d')}",
                report_type=report_type,
                title=f"{report_type.title()} 소싱 리포트",
                period_start=start_date,
                period_end=end_date,
                summary=self._generate_summary(key_findings),
                key_findings=key_findings,
                recommendations=recommendations,
                sales_metrics=sales_metrics,  # 전체 메트릭스는 별도 저장
                market_trends=market_trends[:5],  # 상위 5개
                opportunities=opportunities[:10],  # 상위 10개
                competitors=competitor_updates,
                keywords=keyword_insights,
                created_at=datetime.now(),
            )

            # 저장
            await self._save_report(report)

            return report

        except Exception as e:
            logger.error(f"리포트 생성 오류: {str(e)}")
            return SourcingReport(
                report_id=f"REPORT_ERROR_{datetime.now().strftime('%Y%m%d')}",
                report_type=report_type,
                title="오류 리포트",
                period_start=start_date,
                period_end=end_date,
                summary=f"리포트 생성 중 오류 발생: {str(e)}",
                key_findings=[],
                recommendations=[],
                created_at=datetime.now(),
            )

    async def monitor_opportunities(
        self, opportunity_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        기회 모니터링

        Args:
            opportunity_ids: 모니터링할 기회 ID 목록

        Returns:
            모니터링 결과
        """
        try:
            opportunities = await self._get_opportunities_to_monitor(opportunity_ids)

            monitoring_results = []
            for opportunity in opportunities:
                result = await self._process_single_opportunity_monitoring(opportunity)
                monitoring_results.append(result)

            summary = self._generate_monitoring_summary(opportunities, monitoring_results)

            return {"summary": summary, "results": monitoring_results}

        except Exception as e:
            logger.error(f"기회 모니터링 오류: {str(e)}")
            return {"summary": {}, "results": []}

    async def _get_opportunities_to_monitor(
        self, opportunity_ids: Optional[List[str]]
    ) -> List[ProductOpportunity]:
        """모니터링할 기회 목록을 가져옵니다."""
        if opportunity_ids:
            opportunities = []
            for opp_id in opportunity_ids:
                opp = await self.storage.get("product_opportunities", opp_id)
                if opp:
                    opportunities.append(ProductOpportunity(**opp))
            return opportunities
        else:
            opp_data = await self.storage.list(
                "product_opportunities",
                filters={
                    "expires_at": {"$gte": datetime.now()},
                    "opportunity_score": {"$gte": self.opportunity_threshold},
                },
            )
            return [ProductOpportunity(**o) for o in opp_data]

    async def _process_single_opportunity_monitoring(
        self, opportunity: ProductOpportunity
    ) -> Dict[str, Any]:
        """단일 기회를 모니터링하고 변화를 감지합니다."""
        current_status = await self._reevaluate_opportunity(opportunity)
        changes = self._detect_changes(opportunity, current_status)
        return {
            "opportunity": opportunity,
            "current_status": current_status,
            "changes": changes,
            "action_required": changes["significant_change"],
            "updated_at": datetime.now(),
        }

    def _generate_monitoring_summary(
        self, opportunities: List[ProductOpportunity], monitoring_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """모니터링 결과를 요약합니다."""
        return {
            "total_monitored": len(opportunities),
            "action_required": sum(1 for r in monitoring_results if r["action_required"]),
            "expired": sum(
                1 for o in opportunities if o.expires_at and o.expires_at < datetime.now()
            ),
            "high_potential": sum(
                1 for r in monitoring_results if r["current_status"]["score"] >= 85
            ),
        }

    async def _get_active_categories(self) -> List[str]:
        """활성 카테고리 목록 조회"""
        products = await self.storage.list("products", filters={"status": "active"})

        categories = set()
        for product in products:
            if category := product.get("category_name"):
                categories.add(category)

        return list(categories)

    async def _analyze_keyword_competition(self, keyword: str, category: str) -> Dict[str, Any]:
        """
        키워드 경쟁 분석

        Args:
            keyword: 키워드
            category: 카테고리

        Returns:
            경쟁 분석 결과
        """
        competitor_products = await self._get_competitor_products_for_analysis(category)

        competitors = []
        for product in competitor_products:
            if keyword.lower() in product.get("name", "").lower():
                competitors.append(
                    {
                        "seller": product.get("seller_name"),
                        "price": Decimal(str(product.get("price", 0))),
                        "rating": product.get("rating", 0),
                        "reviews": product.get("review_count", 0),
                    }
                )

        return self._calculate_competition_metrics(competitors)

    async def _get_competitor_products_for_analysis(self, category: str) -> List[Dict[str, Any]]:
        """경쟁 분석을 위한 경쟁사 상품 목록을 가져옵니다."""
        return await self.storage.list(
            "competitor_products", filters={"category": category}, limit=20
        )

    def _calculate_competition_metrics(self, competitors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """경쟁사 관련 통계 및 시장 포화도를 계산합니다."""
        if not competitors:
            return {
                "competitor_count": 0,
                "avg_price": Decimal("0"),
                "avg_rating": 0,
                "market_saturation": "low",
            }

        avg_price = sum(c["price"] for c in competitors) / len(competitors)
        avg_rating = sum(c["rating"] for c in competitors) / len(competitors)

        if len(competitors) > 50:
            saturation = "high"
        elif len(competitors) > 20:
            saturation = "medium"
        else:
            saturation = "low"

        return {
            "competitor_count": len(competitors),
            "avg_price": avg_price,
            "avg_rating": avg_rating,
            "market_saturation": saturation,
            "top_competitors": sorted(competitors, key=lambda x: x["reviews"], reverse=True)[:5],
        }

    async def _analyze_profitability(
        self, keyword: str, metrics: Any, competition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        수익성 분석

        Args:
            keyword: 키워드
            metrics: 키워드 지표
            competition: 경쟁 분석 결과

        Returns:
            수익성 분석 결과
        """
        recommended_price = self._calculate_recommended_price(metrics, competition)
        estimated_cost, estimated_margin = self._calculate_estimated_costs_and_margins(
            recommended_price
        )
        estimated_sales, monthly_revenue, monthly_profit = (
            self._calculate_estimated_sales_and_profit(
                metrics, competition, recommended_price, estimated_margin
            )
        )

        return {
            "recommended_price": recommended_price,
            "estimated_cost": estimated_cost,
            "estimated_margin": estimated_margin,
            "estimated_sales": estimated_sales,
            "monthly_revenue": monthly_revenue,
            "monthly_profit": monthly_profit,
        }

    def _calculate_recommended_price(self, metrics: Any, competition: Dict[str, Any]) -> Decimal:
        """추천 가격을 계산합니다."""
        if competition["avg_price"] > 0:
            return competition["avg_price"] * Decimal("0.95")
        return metrics.average_price

    def _calculate_estimated_costs_and_margins(
        self, recommended_price: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """예상 원가 및 마진을 계산합니다."""
        estimated_cost = recommended_price * Decimal("0.6")
        estimated_margin = recommended_price - estimated_cost
        return estimated_cost, estimated_margin

    def _calculate_estimated_sales_and_profit(
        self,
        metrics: Any,
        competition: Dict[str, Any],
        recommended_price: Decimal,
        estimated_margin: Decimal,
    ) -> Tuple[int, Decimal, Decimal]:
        """예상 판매량 및 월별 수익을 계산합니다."""
        market_share = 0.1 if competition["market_saturation"] == "low" else 0.05
        estimated_sales = int(
            metrics.search_volume * (metrics.conversion_rate or 0.02) * market_share
        )
        monthly_revenue = recommended_price * estimated_sales
        monthly_profit = estimated_margin * estimated_sales
        return estimated_sales, monthly_revenue, monthly_profit

    async def _analyze_suppliers(self, keyword: str, category: str) -> Dict[str, Any]:
        """
        공급사 분석

        Args:
            keyword: 키워드
            category: 카테고리

        Returns:
            공급사 분석 결과
        """
        suppliers = await self._get_suppliers_by_category(category)
        recommended = self._filter_recommended_suppliers(suppliers, keyword)
        diversity = self._calculate_supplier_diversity(suppliers)

        return {"count": len(suppliers), "recommended": recommended[:5], "diversity": diversity}

    async def _get_suppliers_by_category(self, category: str) -> List[Dict[str, Any]]:
        """카테고리별 공급사 목록을 가져옵니다."""
        return await self.storage.list("suppliers", filters={"categories": {"$contains": category}})

    def _filter_recommended_suppliers(
        self, suppliers: List[Dict[str, Any]], keyword: str
    ) -> List[str]:
        """키워드 관련 상품이 있는 공급사를 필터링합니다."""
        recommended = []
        for supplier in suppliers:
            # 실제로는 공급사 API로 확인
            has_related = True
            if has_related:
                recommended.append(supplier.get("name", "Unknown"))
        return recommended

    def _calculate_supplier_diversity(self, suppliers: List[Dict[str, Any]]) -> str:
        """공급사 다양성을 계산합니다."""
        if len(suppliers) > 5:
            return "high"
        elif len(suppliers) > 1:
            return "medium"
        else:
            return "low"

    def _calculate_opportunity_score(
        self,
        keyword_data: Dict[str, Any],
        competition: Dict[str, Any],
        profitability: Dict[str, Any],
        suppliers: Dict[str, Any],
        trend: Optional[MarketTrend],
    ) -> float:
        """기회 점수 계산"""
        score = 0.0

        score += self._calculate_keyword_score(keyword_data)
        score += self._calculate_competition_score(competition)
        score += self._calculate_profitability_score(profitability)
        score += self._calculate_supplier_score(suppliers)
        score += self._calculate_trend_score(trend)

        return min(100, score)

    def _calculate_keyword_score(self, keyword_data: Dict[str, Any]) -> float:
        """키워드 점수를 계산합니다."""
        return keyword_data["opportunity_score"] * 0.3

    def _calculate_competition_score(self, competition: Dict[str, Any]) -> float:
        """경쟁 점수를 계산합니다."""
        if competition["market_saturation"] == "low":
            return 20
        elif competition["market_saturation"] == "medium":
            return 10
        return 0

    def _calculate_profitability_score(self, profitability: Dict[str, Any]) -> float:
        """수익성 점수를 계산합니다."""
        margin_rate = (
            float(profitability["estimated_margin"] / profitability["recommended_price"])
            if profitability["recommended_price"] > 0
            else 0
        )
        return min(30, margin_rate * 100)

    def _calculate_supplier_score(self, suppliers: Dict[str, Any]) -> float:
        """공급사 점수를 계산합니다."""
        if suppliers["count"] > 3:
            return 10
        elif suppliers["count"] > 1:
            return 5
        return 0

    def _calculate_trend_score(self, trend: Optional[MarketTrend]) -> float:
        """트렌드 점수를 계산합니다."""
        if trend and trend.direction == TrendDirection.UP:
            return 10
        elif trend and trend.direction == TrendDirection.STABLE:
            return 5
        return 0

    def _classify_demand(self, search_volume: int) -> str:
        """검색량에 따라 수요 수준을 분류합니다."""
        if search_volume > 10000:
            return "high"
        elif search_volume > 1000:
            return "medium"
        else:
            return "low"

    def _assess_entry_barrier(self, competition: Dict[str, Any]) -> str:
        """진입 장벽 평가"""
        if competition["competitor_count"] > 50 and competition["avg_rating"] > 4.5:
            return "high"
        elif competition["competitor_count"] > 20:
            return "medium"
        else:
            return "low"

    def _analyze_risks(
        self, competition: Dict[str, Any], suppliers: Dict[str, Any], trend: Optional[MarketTrend]
    ) -> List[str]:
        """리스크 분석"""
        risks = []
        risks.extend(self._get_competition_risks(competition))
        risks.extend(self._get_supplier_risks(suppliers))
        risks.extend(self._get_trend_risks(trend))
        risks.extend(self._get_seasonal_risks())
        return risks

    def _get_competition_risks(self, competition: Dict[str, Any]) -> List[str]:
        """경쟁 관련 리스크를 식별합니다."""
        risks = []
        if competition["market_saturation"] == "high":
            risks.append("시장 포화 상태")
        if competition["avg_rating"] > 4.5:
            risks.append("경쟁사 고객 만족도 높음")
        return risks

    def _get_supplier_risks(self, suppliers: Dict[str, Any]) -> List[str]:
        """공급 관련 리스크를 식별합니다."""
        risks = []
        if suppliers["count"] < 2:
            risks.append("공급사 다양성 부족")
        return risks

    def _get_trend_risks(self, trend: Optional[MarketTrend]) -> List[str]:
        """트렌드 관련 리스크를 식별합니다."""
        risks = []
        if trend and trend.direction == TrendDirection.DOWN:
            risks.append("하락 트렌드")
        return risks

    def _get_seasonal_risks(self) -> List[str]:
        """계절성 관련 리스크를 식별합니다."""
        risks = []
        current_month = datetime.now().month
        if current_month in [6, 7, 8]:  # 여름
            risks.append("계절적 수요 변동 가능")
        return risks

    async def _save_opportunity(self, opportunity: ProductOpportunity):
        """기회 저장"""
        opportunity_data = {
            "opportunity_id": opportunity.opportunity_id,
            "opportunity_score": opportunity.opportunity_score,
            "product_name": opportunity.product_name,
            "category": opportunity.category,
            "keywords": opportunity.keywords,
            "market_demand": opportunity.market_demand,
            "competition_level": opportunity.competition_level,
            "entry_barrier": opportunity.entry_barrier,
            "estimated_price": float(opportunity.estimated_price),
            "estimated_cost": float(opportunity.estimated_cost),
            "estimated_margin": float(opportunity.estimated_margin),
            "estimated_monthly_sales": opportunity.estimated_monthly_sales,
            "supplier_count": opportunity.supplier_count,
            "recommended_suppliers": opportunity.recommended_suppliers,
            "risks": opportunity.risks,
            "created_at": opportunity.created_at,
            "expires_at": opportunity.expires_at,
        }
        await self.storage.save("product_opportunities", opportunity_data)

    async def _generate_sales_summary(
        self, categories: List[str], start_date: datetime, end_date: datetime
    ) -> SalesMetrics:
        """판매 요약 생성"""
        all_orders = await self._get_all_orders_for_summary(start_date, end_date)
        total_sales, total_revenue, average_price = self._calculate_overall_sales_metrics(
            all_orders
        )

        growth_rate, trend = await self.sales_analyzer._calculate_growth_rate(
            None, start_date, end_date, total_sales
        )

        return SalesMetrics(
            total_sales=total_sales,
            total_revenue=total_revenue,
            average_price=average_price,
            growth_rate=growth_rate,
            trend=trend,
            period_start=start_date,
            period_end=end_date,
        )

    async def _get_all_orders_for_summary(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """판매 요약을 위한 모든 주문 데이터를 가져옵니다."""
        return await self.storage.list(
            "orders",
            filters={
                "status": {"$in": ["delivered", "shipped"]},
                "order_date": {"$gte": start_date, "$lte": end_date},
            },
        )

    def _calculate_overall_sales_metrics(
        self, orders: List[Dict[str, Any]]
    ) -> Tuple[int, Decimal, Decimal]:
        """전체 판매량, 매출액, 평균 가격을 계산합니다."""
        total_sales = 0
        total_revenue = Decimal("0")
        for order in orders:
            for item in order.get("items", []):
                total_sales += item.get("quantity", 0)
                total_revenue += Decimal(str(item.get("total_price", 0)))
        average_price = total_revenue / total_sales if total_sales > 0 else Decimal("0")
        return total_sales, total_revenue, average_price

    async def _get_competitor_updates(
        self, categories: List[str], since: datetime
    ) -> List[Dict[str, Any]]:
        """
        경쟁사 업데이트 조회

        Args:
            categories: 카테고리 목록
            since: 업데이트 기준 시점

        Returns:
            경쟁사 업데이트 목록
        """
        updates = []
        for category in categories:
            new_competitors = await self._get_new_competitors_for_category(category)
            for comp in new_competitors:
                if comp["discovered_at"] >= since:
                    processed_comp = await self._process_new_competitor(comp)
                    updates.append(processed_comp)

        updates.sort(key=lambda x: x["timestamp"], reverse=True)
        return updates[:20]

    async def _get_new_competitors_for_category(self, category: str) -> List[Dict[str, Any]]:
        """특정 카테고리의 신규 경쟁사를 가져옵니다."""
        return await self.competitor_monitor.track_new_competitors(category)

    async def _process_new_competitor(self, competitor_data: Dict[str, Any]) -> Dict[str, Any]:
        """신규 경쟁사를 분석하고 저장합니다."""
        # 이 부분은 이미 competitor_monitor.track_new_competitors 내에서 처리되므로,
        # 여기서는 단순히 데이터를 반환하는 역할만 수행합니다.
        # 실제 로직은 competitor_monitor._analyze_new_competitor와 _save_competitor에 있습니다.
        return {
            "type": "new_competitor",
            "category": competitor_data["competitor"].get("category"),  # category 필드 추가
            "competitor": competitor_data["competitor"],
            "analysis": competitor_data["analysis"],
            "timestamp": competitor_data["discovered_at"],
        }

    async def _generate_keyword_insights(
        self, categories: List[str], days: int
    ) -> List[Dict[str, Any]]:
        """
        키워드 인사이트 생성

        Args:
            categories: 카테고리 목록
            days: 분석 기간 (일)

        Returns:
            키워드 인사이트 목록
        """
        insights = []
        for category in categories:
            top_keywords = await self._get_top_keywords_for_category(category, days)
            if top_keywords:
                trends = await self._analyze_keyword_trends(top_keywords, days)
                insights.append(
                    {
                        "category": category,
                        "top_keywords": [k["keyword"] for k in top_keywords],
                        "rising_keywords": trends["summary"]["rising_keywords"],
                        "declining_keywords": trends["summary"]["declining_keywords"],
                    }
                )
        return insights

    async def _get_top_keywords_for_category(
        self, category: str, days: int
    ) -> List[Dict[str, Any]]:
        """특정 카테고리의 상위 키워드를 가져옵니다."""
        return await self.storage.list(
            "keyword_metrics",
            filters={
                "category": category,
                "analyzed_at": {"$gte": datetime.now() - timedelta(days=days)},
            },
            limit=10,
        )

    async def _analyze_keyword_trends(
        self, top_keywords: List[Dict[str, Any]], days: int
    ) -> Dict[str, Any]:
        """키워드 트렌드를 분석합니다."""
        keyword_list = [k["keyword"] for k in top_keywords]
        return await self.keyword_researcher.track_keyword_trends(keyword_list, days)

    def _extract_key_findings(
        self,
        sales_metrics: SalesMetrics,
        trends: List[MarketTrend],
        opportunities: List[ProductOpportunity],
        competitor_updates: List[Dict[str, Any]],
        keyword_insights: List[Dict[str, Any]],
    ) -> List[str]:
        """주요 발견사항 추출"""
        findings = []
        findings.extend(self._get_sales_findings(sales_metrics))
        findings.extend(self._get_trend_findings(trends))
        findings.extend(self._get_opportunity_findings(opportunities))
        findings.extend(self._get_competitor_findings(competitor_updates))
        findings.extend(self._get_keyword_findings(keyword_insights))
        return findings

    def _get_sales_findings(self, sales_metrics: SalesMetrics) -> List[str]:
        """판매 관련 발견사항을 추출합니다."""
        if sales_metrics and sales_metrics.total_sales > 0:
            return [
                f"총 {sales_metrics.total_sales}개 판매, 매출 {sales_metrics.total_revenue:,.0f}원 달성"
            ]
        return []

    def _get_trend_findings(self, trends: List[MarketTrend]) -> List[str]:
        """트렌드 관련 발견사항을 추출합니다."""
        strong_trends = [t for t in trends if t.strength > 50]
        if strong_trends:
            return [f"{len(strong_trends)}개 카테고리에서 강한 트렌드 감지"]
        return []

    def _get_opportunity_findings(self, opportunities: List[ProductOpportunity]) -> List[str]:
        """기회 관련 발견사항을 추출합니다."""
        if opportunities:
            high_score = [o for o in opportunities if o.opportunity_score >= 85]
            if high_score:
                return [f"{len(high_score)}개의 고득점 상품 기회 발견"]
        return []

    def _get_competitor_findings(self, competitor_updates: List[Dict[str, Any]]) -> List[str]:
        """경쟁사 관련 발견사항을 추출합니다."""
        new_competitors = [u for u in competitor_updates if u["type"] == "new_competitor"]
        if new_competitors:
            return [f"{len(new_competitors)}개 신규 경쟁사 진입"]
        return []

    def _get_keyword_findings(self, keyword_insights: List[Dict[str, Any]]) -> List[str]:
        """키워드 관련 발견사항을 추출합니다."""
        rising_keywords = []
        for insight in keyword_insights:
            rising_keywords.extend(insight.get("rising_keywords", []))
        if rising_keywords:
            return [f"{len(set(rising_keywords))}개 상승 키워드 확인"]
        return []

    def _generate_recommendations(
        self,
        key_findings: List[str],
        opportunities: List[ProductOpportunity],
        trends: List[MarketTrend],
    ) -> List[str]:
        """추천사항 생성"""
        recommendations = []
        recommendations.extend(self._get_opportunity_recommendations(opportunities))
        recommendations.extend(self._get_trend_recommendations(trends))
        recommendations.extend(self._get_competition_avoidance_recommendations(opportunities))
        recommendations.extend(self._get_supplier_diversification_recommendations(opportunities))
        return recommendations

    def _get_opportunity_recommendations(
        self, opportunities: List[ProductOpportunity]
    ) -> List[str]:
        """기회 기반 추천을 생성합니다."""
        if opportunities:
            top_opp = opportunities[0]
            return [
                f"{top_opp.category} 카테고리의 '{top_opp.keywords[0]}' 상품 출시 검토 (예상 월 수익: {top_opp.estimated_margin * top_opp.estimated_monthly_sales:,.0f}원)"
            ]
        return []

    def _get_trend_recommendations(self, trends: List[MarketTrend]) -> List[str]:
        """트렌드 기반 추천을 생성합니다."""
        up_trends = [t for t in trends if t.direction == TrendDirection.UP and t.strength > 50]
        if up_trends:
            return [
                f"{up_trends[0].category} 카테고리 확대 고려 (상승 트렌드 {up_trends[0].strength:.0f}% 강도)"
            ]
        return []

    def _get_competition_avoidance_recommendations(
        self, opportunities: List[ProductOpportunity]
    ) -> List[str]:
        """경쟁 회피 추천을 생성합니다."""
        high_competition = [o for o in opportunities if o.competition_level == "high"]
        if len(high_competition) > len(opportunities) * 0.5:
            return ["경쟁이 낮은 니치 시장 탐색 강화 필요"]
        return []

    def _get_supplier_diversification_recommendations(
        self, opportunities: List[ProductOpportunity]
    ) -> List[str]:
        """공급사 다각화 추천을 생성합니다."""
        low_supplier = [o for o in opportunities if o.supplier_count < 3]
        if low_supplier:
            return ["안정적인 공급망 확보를 위한 추가 공급사 발굴 필요"]
        return []

    def _generate_summary(self, key_findings: List[str]) -> str:
        """주요 발견사항을 바탕으로 요약을 생성합니다."""
        if not key_findings:
            return "분석 기간 동안 특별한 발견사항이 없습니다."

        summary_parts = key_findings[:3]
        summary = "이번 분석 기간 동안 " + ", ".join(summary_parts)

        if len(key_findings) > 3:
            summary += f" 등 총 {len(key_findings)}개의 주요 발견사항이 있었습니다."
        else:
            summary += "."

        return summary

    async def _save_report(self, report: SourcingReport):
        """리포트 저장"""
        report_data = self._build_report_data(report)

        # 상세 데이터는 별도 저장
        if report.sales_metrics:
            report_data["sales_metrics_id"] = await self._save_metrics(report.sales_metrics)

        await self.storage.save("sourcing_reports", report_data)

        # 오래된 리포트 정리
        await self._cleanup_old_reports()

    def _build_report_data(self, report: SourcingReport) -> Dict[str, Any]:
        """리포트 데이터를 구성합니다."""
        return {
            "report_id": report.report_id,
            "report_type": report.report_type,
            "title": report.title,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "summary": report.summary,
            "key_findings": report.key_findings,
            "recommendations": report.recommendations,
            "created_at": report.created_at,
        }

    async def _save_metrics(self, metrics: Dict[str, Any]) -> str:
        """지표 저장"""
        metrics_id = f"METRICS_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        await self.storage.save(
            "report_metrics",
            {"metrics_id": metrics_id, "data": metrics, "created_at": datetime.now()},
        )
        return metrics_id

    async def _cleanup_old_reports(self):
        """지정된 보존 기간보다 오래된 리포트를 정리합니다."""
        cutoff_date = datetime.now() - timedelta(days=self.report_retention_days)

        old_reports = await self.storage.list(
            "sourcing_reports", filters={"created_at": {"$lt": cutoff_date}}
        )

        for report in old_reports:
            await self.storage.delete("sourcing_reports", report["report_id"])

    async def _reevaluate_opportunity(self, opportunity: ProductOpportunity) -> Dict[str, Any]:
        """기회 재평가"""
        current_metrics, current_competition = await self._get_current_opportunity_metrics(
            opportunity
        )
        new_score = self._calculate_score_change(opportunity, current_metrics, current_competition)

        return {
            "score": new_score,
            "search_volume": current_metrics.search_volume,
            "competition": current_competition["market_saturation"],
            "metrics": current_metrics,
        }

    async def _get_current_opportunity_metrics(
        self, opportunity: ProductOpportunity
    ) -> Tuple[Any, Dict[str, Any]]:
        """현재 키워드 지표와 경쟁 상황을 가져옵니다."""
        current_metrics = await self.keyword_researcher.research_keyword(
            opportunity.keywords[0], opportunity.category
        )
        current_competition = await self._analyze_keyword_competition(
            opportunity.keywords[0], opportunity.category
        )
        return current_metrics, current_competition

    def _calculate_score_change(
        self,
        opportunity: ProductOpportunity,
        current_metrics: Any,
        current_competition: Dict[str, Any],
    ) -> float:
        """점수 변화를 계산합니다."""
        score_change = 0
        if current_metrics.search_volume < opportunity.estimated_monthly_sales * 10:
            score_change -= 10
        if current_competition["competitor_count"] > 50:
            score_change -= 15
        return max(0, opportunity.opportunity_score + score_change)

    def _detect_changes(
        self, opportunity: ProductOpportunity, current_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        """변화 감지"""
        score_change = self._calculate_score_difference(opportunity, current_status)
        competition_changed = self._check_competition_change(opportunity, current_status)
        significant_change = self._is_significant_change(score_change, opportunity, current_status)

        return {
            "score_change": score_change,
            "competition_change": competition_changed,
            "significant_change": significant_change,
        }

    def _calculate_score_difference(
        self, opportunity: ProductOpportunity, current_status: Dict[str, Any]
    ) -> float:
        """기회 점수 차이를 계산합니다."""
        return current_status["score"] - opportunity.opportunity_score

    def _check_competition_change(
        self, opportunity: ProductOpportunity, current_status: Dict[str, Any]
    ) -> bool:
        """경쟁 수준 변화를 확인합니다."""
        return current_status["competition"] != opportunity.competition_level

    def _is_significant_change(
        self, score_change: float, opportunity: ProductOpportunity, current_status: Dict[str, Any]
    ) -> bool:
        """중요한 변화인지 판단합니다."""
        if abs(score_change) > 15:
            return True
        if opportunity.competition_level == "low" and current_status["competition"] == "high":
            return True
        return False
