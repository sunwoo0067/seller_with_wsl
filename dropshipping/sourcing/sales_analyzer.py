"""
판매 분석 시스템
마켓플레이스별 판매 데이터 분석 및 트렌드 파악
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import statistics

from loguru import logger

from dropshipping.models.sourcing import SalesMetrics, TrendDirection, MarketTrend
from dropshipping.storage.base import BaseStorage


class SalesAnalyzer:
    """판매 분석기"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 분석 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # 분석 설정
        self.min_data_points = self.config.get("min_data_points", 7)  # 최소 데이터 포인트
        self.trend_threshold = self.config.get("trend_threshold", 0.05)  # 트렌드 임계값 5%
        self.seasonality_window = self.config.get("seasonality_window", 365)  # 계절성 분석 기간
        
        # 캐시
        self._cache = {}
    
    async def analyze_product_sales(
        self,
        product_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> SalesMetrics:
        """
        상품별 판매 분석
        
        Args:
            product_id: 상품 ID
            start_date: 시작일
            end_date: 종료일
            
        Returns:
            판매 지표
        """
        try:
            orders, total_sales, total_revenue, average_price = await self._get_product_orders_and_calculate_metrics(product_id, start_date, end_date)
            
            if not orders:
                return self._empty_metrics(start_date, end_date)
            
            growth_rate, trend = await self._calculate_growth_rate(
                product_id,
                start_date,
                end_date,
                total_sales
            )
            
            market_share = await self._estimate_market_share(
                product_id,
                start_date,
                end_date,
                total_sales
            )
            
            return SalesMetrics(
                total_sales=total_sales,
                total_revenue=total_revenue,
                average_price=average_price,
                growth_rate=growth_rate,
                trend=trend,
                market_share=market_share,
                period_start=start_date,
                period_end=end_date
            )
            
        except Exception as e:
            logger.error(f"상품 판매 분석 오류: {str(e)}")
            return self._empty_metrics(start_date, end_date)

    async def _get_product_orders_and_calculate_metrics(
        self,
        product_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[List[Dict[str, Any]], int, Decimal, Decimal]:
        """상품 주문을 가져오고 기본 판매 지표를 계산합니다."""
        orders = await self._get_product_orders(product_id, start_date, end_date)
        
        total_sales = sum(item.get("quantity", 0) for order in orders for item in order.get("items", []) if item.get("product_id") == product_id)
        total_revenue = sum(
            Decimal(str(item.get("total_price", 0)))
            for order in orders
            for item in order.get("items", [])
            if item.get("product_id") == product_id
        )
        average_price = total_revenue / total_sales if total_sales > 0 else Decimal("0")
        
        return orders, total_sales, total_revenue, average_price
    
    async def analyze_category_sales(
        self,
        category: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        카테고리별 판매 분석
        
        Args:
            category: 카테고리
            start_date: 시작일
            end_date: 종료일
            
        Returns:
            카테고리 판매 분석 결과
        """
        try:
            products = await self.storage.list("products", filters={"category_name": category})
            product_metrics = await self._get_category_products_and_metrics(products, start_date, end_date)
            
            total_sales, total_revenue, top_products = self._calculate_category_overall_metrics(product_metrics)
            price_distribution = self._calculate_price_distribution(product_metrics)
            
            return {
                "category": category,
                "period": {"start": start_date, "end": end_date},
                "total_products": len(products),
                "total_sales": total_sales,
                "total_revenue": total_revenue,
                "top_products": top_products,
                "price_distribution": price_distribution,
                "product_metrics": product_metrics
            }
            
        except Exception as e:
            logger.error(f"카테고리 판매 분석 오류: {str(e)}")
            return {}

    async def _get_category_products_and_metrics(self, products: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """카테고리 상품별 판매 지표를 가져옵니다."""
        product_metrics = []
        for product in products:
            metrics = await self.analyze_product_sales(product["id"], start_date, end_date)
            product_metrics.append({"product_id": product["id"], "product_name": product["name"], "metrics": metrics})
        return product_metrics

    def _calculate_category_overall_metrics(self, product_metrics: List[Dict[str, Any]]) -> Tuple[int, Decimal, List[Dict[str, Any]]]:
        """카테고리 전체 지표를 계산합니다."""
        total_sales = sum(m["metrics"].total_sales for m in product_metrics)
        total_revenue = sum(m["metrics"].total_revenue for m in product_metrics)
        top_products = sorted(product_metrics, key=lambda x: x["metrics"].total_sales, reverse=True)[:10]
        return total_sales, total_revenue, top_products

    def _calculate_price_distribution(self, product_metrics: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        """가격 분포를 계산합니다."""
        prices = [m["metrics"].average_price for m in product_metrics if m["metrics"].average_price > 0]
        if not prices:
            return {"min": Decimal("0"), "max": Decimal("0"), "avg": Decimal("0"), "median": Decimal("0")}
        
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        median_price = Decimal(str(statistics.median(prices)))
        return {"min": min_price, "max": max_price, "avg": avg_price, "median": median_price}
    
    async def detect_trends(
        self,
        lookback_days: int = 30
    ) -> List[MarketTrend]:
        """
        시장 트렌드 감지
        
        Args:
            lookback_days: 분석 기간 (일)
            
        Returns:
            트렌드 목록
        """
        trends = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        try:
            categories = await self._get_active_categories()
            if not categories:
                return []

            for category in categories:
                daily_sales = await self._get_daily_sales_by_category(
                    category,
                    start_date,
                    end_date
                )
                
                if len(daily_sales) < self.min_data_points:
                    continue
                
                trend_info = self._analyze_trend(daily_sales)
                
                if trend_info["strength"] > 30:
                    trending_keywords = await self._extract_trending_keywords(
                        category,
                        start_date,
                        end_date
                    )
                    
                    trending_products = await self._get_trending_products(
                        category,
                        start_date,
                        end_date
                    )
                    
                    trend = MarketTrend(
                        trend_id=f"TREND_{category}_{datetime.now().strftime('%Y%m%d')}",
                        name=f"{category} 트렌드",
                        category=category,
                        strength=trend_info["strength"],
                        direction=trend_info["direction"],
                        momentum=trend_info["momentum"],
                        trending_keywords=trending_keywords[:10],
                        trending_products=trending_products[:5],
                        forecast_period=7,
                        forecast_direction=trend_info["forecast"],
                        confidence_level=trend_info["confidence"],
                        analyzed_at=datetime.now(),
                        data_points=len(daily_sales)
                    )
                    
                    trends.append(trend)
            
            overall_trend = await self._analyze_overall_market_trend(
                start_date,
                end_date
            )
            if overall_trend:
                trends.insert(0, overall_trend)
            
            return trends
            
        except Exception as e:
            logger.error(f"트렌드 감지 오류: {str(e)}")
            return trends
    
    async def calculate_seasonality(
        self,
        product_id: str
    ) -> Dict[str, float]:
        """
        계절성 분석
        
        Args:
            product_id: 상품 ID
            
        Returns:
            월별 계절성 지수
        """
        try:
            monthly_sales = await self._get_monthly_sales_data(product_id)
            seasonality = self._calculate_seasonality_index(monthly_sales)
            return seasonality
            
        except Exception as e:
            logger.error(f"계절성 분석 오류: {str(e)}")
            return {str(i): 1.0 for i in range(1, 13)}

    async def _get_monthly_sales_data(self, product_id: str) -> Dict[int, List[int]]:
        """월별 판매 데이터를 가져옵니다."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.seasonality_window)
        monthly_sales = defaultdict(list)
        
        current = start_date
        while current < end_date:
            month_end = current.replace(day=28) + timedelta(days=4)
            month_end = month_end - timedelta(days=month_end.day)
            
            orders = await self._get_product_orders(product_id, current, month_end)
            sales = sum(item.get("quantity", 0) for order in orders for item in order.get("items", []) if item.get("product_id") == product_id)
            monthly_sales[current.month].append(sales)
            current = month_end + timedelta(days=1)
        return monthly_sales

    def _calculate_seasonality_index(self, monthly_sales: Dict[int, List[int]]) -> Dict[str, float]:
        """월별 계절성 지수를 계산합니다."""
        seasonality = {}
        total_avg = sum(sum(sales) for sales in monthly_sales.values()) / 12 if monthly_sales else 100
        
        for month in range(1, 13):
            month_str = str(month)
            if month in monthly_sales and monthly_sales[month]:
                month_avg = sum(monthly_sales[month]) / len(monthly_sales[month])
                seasonality[month_str] = month_avg / total_avg if total_avg > 0 else 1.0
            else:
                seasonality[month_str] = 1.0
        return seasonality
    
    async def _get_product_orders(
        self,
        product_id: Optional[str],
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """상품 주문 조회"""
        all_orders = await self._get_all_orders_in_period(start_date, end_date)
        
        if product_id is None:
            return all_orders

        product_orders = []
        for order in all_orders:
            for item in order.get("items", []):
                if item.get("product_id") == product_id:
                    product_orders.append(order)
                    break
        
        return product_orders

    async def _get_all_orders_in_period(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """특정 기간 내의 모든 주문을 가져옵니다."""
        return await self.storage.list(
            "orders",
            filters={
                "status": {"$in": ["delivered", "shipped"]},
                "order_date": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
        )
    
    async def _calculate_growth_rate(
        self,
        product_id: Optional[str],
        start_date: datetime,
        end_date: datetime,
        current_sales: int
    ) -> Tuple[float, TrendDirection]:
        """
        성장률 계산
        
        Args:
            product_id: 상품 ID (전체 판매량 계산 시 None)
            start_date: 현재 기간 시작일
            end_date: 현재 기간 종료일
            current_sales: 현재 기간 판매량
            
        Returns:
            성장률 및 트렌드 방향
        """
        prev_sales = await self._get_previous_period_sales(product_id, start_date, end_date)
        
        if prev_sales > 0:
            growth_rate = ((current_sales - prev_sales) / prev_sales) * 100
        else:
            growth_rate = 100.0 if current_sales > 0 else 0.0
        
        trend = self._determine_trend_direction(growth_rate)
        
        return growth_rate, trend

    async def _get_previous_period_sales(self, product_id: Optional[str], current_start_date: datetime, current_end_date: datetime) -> int:
        """이전 기간의 판매량을 가져옵니다."""
        period_length = (current_end_date - current_start_date).days
        prev_start = current_start_date - timedelta(days=period_length)
        prev_end = current_start_date - timedelta(days=1)
        
        prev_orders = await self._get_product_orders(product_id, prev_start, prev_end)
        
        if product_id:
            return sum(item.get("quantity", 0) for order in prev_orders for item in order.get("items", []) if item.get("product_id") == product_id)
        else:
            return sum(item.get("quantity", 0) for order in prev_orders for item in order.get("items", []))

    def _determine_trend_direction(self, growth_rate: float) -> TrendDirection:
        """성장률에 따라 트렌드 방향을 결정합니다."""
        if growth_rate > self.trend_threshold * 100:
            return TrendDirection.UP
        elif growth_rate < -self.trend_threshold * 100:
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE
    
    async def _estimate_market_share(
        self,
        product_id: str,
        start_date: datetime,
        end_date: datetime,
        product_sales: int
    ) -> float:
        """시장 점유율 추정 (간단 구현)"""
        product = await self.storage.get("products", product_id)
        if not product:
            return 0.0
        
        category = product.get("category_name", "")
        total_category_sales = await self._get_category_total_sales(category, start_date, end_date)
        
        return (product_sales / total_category_sales * 100) if total_category_sales > 0 else 0.0

    async def _get_category_total_sales(self, category: str, start_date: datetime, end_date: datetime) -> int:
        """특정 카테고리의 총 판매량을 가져옵니다."""
        category_products = await self.storage.list("products", filters={"category_name": category})
        total_sales = 0
        for p in category_products:
            orders = await self._get_product_orders(p["id"], start_date, end_date)
            total_sales += sum(item.get("quantity", 0) for order in orders for item in order.get("items", []) if item.get("product_id") == p["id"])
        return total_sales
    
    def _empty_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> SalesMetrics:
        """빈 판매 지표"""
        return SalesMetrics(
            total_sales=0,
            total_revenue=Decimal("0"),
            average_price=Decimal("0"),
            growth_rate=0.0,
            trend=TrendDirection.STABLE,
            period_start=start_date,
            period_end=end_date
        )
    
    async def _get_active_categories(self) -> List[str]:
        """활성 상태인 상품들의 카테고리 목록을 가져옵니다."""
        products = await self.storage.list("products", filters={"status": "active"})
        categories = {product.get("category_name") for product in products if product.get("category_name")}
        return list(categories)
    
    async def _get_daily_sales_by_category(
        self,
        category: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Tuple[datetime, int]]:
        """카테고리별 일별 판매 데이터"""
        daily_sales = []
        
        current = start_date
        while current <= end_date:
            next_day = current + timedelta(days=1)
            
            # 해당일 주문 조회
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
            
            # 카테고리 상품 판매량 계산
            day_sales = 0
            for order in orders:
                for item in order.get("items", []):
                    product = await self.storage.get(
                        "products",
                        item.get("product_id")
                    )
                    if product and product.get("category_name") == category:
                        day_sales += item.get("quantity", 0)
            
            daily_sales.append((current, day_sales))
            current = next_day
        
        return daily_sales
    
    def _analyze_trend(
        self,
        daily_sales: List[Tuple[datetime, int]]
    ) -> Dict[str, Any]:
        """트렌드 분석"""
        if len(daily_sales) < 2:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "momentum": 0.0,
                "forecast": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        # 이동평균 계산
        sales_values = [s[1] for s in daily_sales]
        
        # 7일 이동평균
        ma7 = []
        for i in range(6, len(sales_values)):
            ma7.append(sum(sales_values[i-6:i+1]) / 7)
        
        if len(ma7) < 2:
            return {
                "strength": 0.0,
                "direction": TrendDirection.STABLE,
                "momentum": 0.0,
                "forecast": TrendDirection.STABLE,
                "confidence": 0.0
            }
        
        # 트렌드 강도 (기울기)
        x = list(range(len(ma7)))
        y = ma7
        
        # 간단한 선형 회귀
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        if n * sum_x2 - sum_x ** 2 == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        # 트렌드 방향
        if slope > 0.1:
            direction = TrendDirection.UP
        elif slope < -0.1:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE
        
        # 트렌드 강도 (0-100)
        avg_sales = sum(sales_values) / len(sales_values)
        strength = min(100, abs(slope) / (avg_sales + 1) * 100)
        
        # 모멘텀 (최근 변화율)
        recent_change = (ma7[-1] - ma7[-3]) / (ma7[-3] + 1) * 100 if len(ma7) >= 3 else 0
        momentum = min(100, abs(recent_change))
        
        # 예측 (간단히 현재 트렌드 유지)
        forecast = direction
        
        # 신뢰도 (데이터 포인트와 변동성 기반)
        variance = statistics.variance(sales_values) if len(sales_values) > 1 else 0
        cv = (variance ** 0.5) / (avg_sales + 1) if avg_sales > 0 else 1
        confidence = max(0, min(100, (1 - cv) * 100 * (len(daily_sales) / 30)))
        
        return {
            "strength": strength,
            "direction": direction,
            "momentum": momentum,
            "forecast": forecast,
            "confidence": confidence
        }
    
    async def _extract_trending_keywords(
        self,
        category: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[str]:
        """트렌딩 키워드 추출"""
        product_names = await self._get_product_names_for_keyword_extraction(category)
        keyword_counts = self._count_keywords_in_names(product_names)
        
        sorted_keywords = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [k[0] for k in sorted_keywords[:20]]

    async def _get_product_names_for_keyword_extraction(self, category: str) -> List[str]:
        """키워드 추출을 위한 상품 이름 목록을 가져옵니다."""
        products = await self.storage.list("products", filters={"category_name": category})
        return [product.get("name", "") for product in products]

    def _count_keywords_in_names(self, product_names: List[str]) -> Dict[str, int]:
        """상품 이름에서 키워드 빈도를 계산합니다."""
        keyword_counts = defaultdict(int)
        for name in product_names:
            keywords = name.split()
            for keyword in keywords:
                if len(keyword) > 2:
                    keyword_counts[keyword.lower()] += 1
        return keyword_counts
    
    async def _get_trending_products(
        self,
        category: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        트렌딩 상품 조회
        
        Args:
            category: 카테고리
            start_date: 시작일
            end_date: 종료일
            
        Returns:
            트렌딩 상품 목록
        """
        products = await self.storage.list("products", filters={"category_name": category})
        product_sales = await self._get_product_sales_metrics(products[:20], start_date, end_date)
        trending = self._sort_trending_products(product_sales)
        return trending

    async def _get_product_sales_metrics(self, products: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """주어진 상품 목록에 대한 판매 지표를 가져옵니다."""
        product_sales = []
        for product in products:
            metrics = await self.analyze_product_sales(product["id"], start_date, end_date)
            if metrics.total_sales > 0:
                product_sales.append({
                    "product_id": product["id"],
                    "name": product["name"],
                    "sales": metrics.total_sales,
                    "growth_rate": metrics.growth_rate,
                    "trend": metrics.trend
                })
        return product_sales

    def _sort_trending_products(self, product_sales: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """트렌딩 상품을 성장률 기준으로 정렬합니다."""
        return sorted(product_sales, key=lambda x: x["growth_rate"], reverse=True)
    
    async def _analyze_overall_market_trend(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[MarketTrend]:
        """전체 시장 트렌드 분석"""
        try:
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
                day_sales = sum(
                    item.get("quantity", 0)
                    for order in orders
                    for item in order.get("items", [])
                )
                daily_sales.append((current, day_sales))
                current = next_day

            if not daily_sales or len(daily_sales) < self.min_data_points:
                return None

            trend_info = self._analyze_trend(daily_sales)
            all_keywords = []
            categories = await self._get_active_categories()
            for category in categories[:5]:
                keywords = await self._extract_trending_keywords(
                    category,
                    start_date,
                    end_date
                )
                all_keywords.extend(keywords[:5])

            return MarketTrend(
                trend_id=f"TREND_OVERALL_{datetime.now().strftime('%Y%m%d')}",
                name="전체 시장 트렌드",
                category="ALL",
                strength=trend_info["strength"],
                direction=trend_info["direction"],
                momentum=trend_info["momentum"],
                trending_keywords=list(set(all_keywords))[:10],
                trending_products=[],
                forecast_period=7,
                forecast_direction=trend_info["forecast"],
                confidence_level=trend_info["confidence"],
                analyzed_at=datetime.now(),
                data_points=len(daily_sales)
            )

        except Exception as e:
            logger.error(f"전체 시장 트렌드 분석 오류: {str(e)}")
            return None