"""
소싱 인텔리전스 시스템 통합 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import pytest

from dropshipping.storage.base import BaseStorage
from dropshipping.models.sourcing import (
    SalesMetrics, CompetitorInfo, KeywordMetrics, ProductOpportunity,
    MarketTrend, TrendDirection, SourcingReport
)
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.trend_predictor import TrendPredictor
from dropshipping.sourcing.dashboard import SourcingDashboard


class MockStorage(BaseStorage):
    """테스트용 Mock Storage"""
    
    def __init__(self):
        super().__init__()
        self.data = {}
        self.id_counter = 1
    
    async def create(self, table: str, data: dict) -> dict:
        if table not in self.data:
            self.data[table] = {}
        
        data["id"] = str(self.id_counter)
        self.id_counter += 1
        data["created_at"] = datetime.now()
        data["updated_at"] = datetime.now()
        
        self.data[table][data["id"]] = data
        return data
    
    async def get(self, table: str, id: str = None, filters: dict = None) -> dict:
        if table not in self.data:
            return None
        
        if id:
            return self.data[table].get(id)
        
        if filters:
            for item in self.data[table].values():
                match = True
                for key, value in filters.items():
                    if item.get(key) != value:
                        match = False
                        break
                if match:
                    return item
        
        return None
    
    async def list(self, table: str, filters: dict = None, limit: int = None) -> list:
        if table not in self.data:
            return []
        
        items = list(self.data[table].values())
        
        if filters:
            filtered_items = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if isinstance(value, dict):
                        # 날짜 범위 필터
                        if "$gte" in value and "$lte" in value:
                            item_value = item.get(key)
                            if isinstance(item_value, str):
                                item_value = datetime.fromisoformat(item_value)
                            
                            if not (value["$gte"] <= item_value <= value["$lte"]):
                                match = False
                                break
                        elif "$gte" in value and "$lt" in value:
                            item_value = item.get(key)
                            if isinstance(item_value, str):
                                item_value = datetime.fromisoformat(item_value)
                            
                            if not (value["$gte"] <= item_value < value["$lt"]):
                                match = False
                                break
                        elif "$in" in value:
                            if item.get(key) not in value["$in"]:
                                match = False
                                break
                        elif "$contains" in value:
                            if value["$contains"] not in item.get(key, ""):
                                match = False
                                break
                    elif item.get(key) != value:
                        match = False
                        break
                if match:
                    filtered_items.append(item)
            items = filtered_items
        
        if limit:
            items = items[:limit]
        
        return items
    
    async def update(self, table: str, id: str, data: dict) -> dict:
        if table not in self.data or id not in self.data[table]:
            return None
        
        self.data[table][id].update(data)
        self.data[table][id]["updated_at"] = datetime.now()
        return self.data[table][id]
    
    async def delete(self, table: str, id: str) -> bool:
        if table not in self.data or id not in self.data[table]:
            return False
        
        del self.data[table][id]
        return True
    
    # BaseStorage 추상 메서드 구현 (추가)
    async def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        return []

    async def get_supplier_code(self, supplier_id: str) -> str:
        return supplier_id

    async def get_marketplace_code(self, marketplace_id: str) -> str:
        return marketplace_id

    async def upsert(self, table_name: str, records: List[Dict[str, Any]], on_conflict: str) -> List[Dict[str, Any]]:
        # 간단한 upsert mock
        if table_name not in self.data:
            self.data[table_name] = {}
        upserted_records = []
        for record in records:
            # 실제 DB의 on_conflict 로직을 완벽히 모방하기는 어려우므로, 간단히 ID 기반으로 처리
            # 실제 테스트에서는 이 부분이 중요하면 더 정교하게 mock해야 함
            record_id = record.get("id") or str(self.id_counter)
            if record_id not in self.data[table_name]:
                self.id_counter += 1
                record["id"] = record_id
                record["created_at"] = datetime.now()
            record["updated_at"] = datetime.now()
            self.data[table_name][record_id] = record
            upserted_records.append(record)
        return upserted_records

    async def get_marketplace_upload(self, product_id: str, marketplace: str) -> Optional[Dict[str, Any]]:
        # Mock 구현: 항상 None 반환 (업로드 기록 없음 가정)
        return None

    async def save_marketplace_upload(self, record: Dict[str, Any]):
        # Mock 구현: 아무것도 하지 않음
        pass

    async def save_raw_product(self, supplier: str, product_data: dict) -> dict:
        return await self.create("raw_products", product_data)
    
    async def save_processed_product(self, product_data: dict) -> dict:
        return await self.create("products", product_data)
    
    async def get_raw_product(self, supplier: str, product_id: str) -> dict:
        return await self.get("raw_products", filters={"supplier": supplier, "product_id": product_id})
    
    async def get_processed_product(self, product_id: str) -> dict:
        return await self.get("products", product_id)
    
    async def list_raw_products(self, supplier: str, limit: int = 100) -> list:
        return await self.list("raw_products", filters={"supplier": supplier}, limit=limit)
    
    async def update_status(self, supplier: str, product_id: str, status: str) -> bool:
        product = await self.get_raw_product(supplier, product_id)
        if product:
            await self.update("raw_products", product["id"], {"status": status})
            return True
        return False
    
    async def exists_by_hash(self, data_hash: str) -> bool:
        products = await self.list("raw_products")
        return any(p.get("data_hash") == data_hash for p in products)
    
    async def get_stats(self, supplier: str) -> dict:
        products = await self.list("raw_products", filters={"supplier": supplier})
        return {
            "total": len(products),
            "processed": len([p for p in products if p.get("status") == "processed"]),
            "failed": len([p for p in products if p.get("status") == "failed"])
        }


@pytest.fixture
def storage():
    return MockStorage()


@pytest.fixture
async def setup_test_data(storage):
    """테스트 데이터 설정"""
    # 상품 데이터
    products = [
        {
            "id": "1",
            "name": "무선 이어폰 블루투스 5.0",
            "category_name": "전자제품",
            "price": 29900,
            "stock": 100,
            "status": "active"
        },
        {
            "id": "2",
            "name": "스마트 체중계 블루투스 연동",
            "category_name": "헬스케어",
            "price": 39900,
            "stock": 50,
            "status": "active"
        },
        {
            "id": "3",
            "name": "휴대용 미니 가습기",
            "category_name": "생활가전",
            "price": 19900,
            "stock": 200,
            "status": "active"
        }
    ]
    
    for product in products:
        await storage.create("products", product)
    
    # 주문 데이터
    orders = []
    for i in range(30):
        order_date = datetime.now() - timedelta(days=i)
        order = {
            "id": str(i + 1),
            "order_date": order_date,
            "status": "delivered",
            "items": [
                {
                    "product_id": "1",
                    "quantity": 2,
                    "unit_price": 29900,
                    "total_price": 59800
                }
            ],
            "customer": {
                "name": f"고객{i + 1}",
                "phone": f"010-1234-{5000 + i:04d}"
            }
        }
        orders.append(order)
    
    for order in orders:
        await storage.create("orders", order)
    
    # 경쟁사 데이터
    competitors = [
        {
            "competitor_id": "COMP001",
            "name": "테크샵",
            "marketplace": "coupang",
            "category": "전자제품"
        },
        {
            "competitor_id": "COMP002",
            "name": "헬스마켓",
            "marketplace": "11st",
            "category": "헬스케어"
        }
    ]
    
    for comp in competitors:
        await storage.create("competitors", comp)
    
    # 경쟁사 상품 데이터
    competitor_products = [
        {
            "seller_id": "COMP001",
            "seller_name": "테크샵",
            "marketplace": "coupang",
            "category": "전자제품",
            "name": "프리미엄 무선 이어폰",
            "price": 35000,
            "rating": 4.5,
            "review_count": 1200,
            "min_price": 35000,
            "max_price": 35000,
            "shipping_method": "로켓배송",
            "delivery_days": 1
        },
        {
            "seller_id": "COMP002",
            "seller_name": "헬스마켓",
            "marketplace": "11st",
            "category": "헬스케어",
            "name": "AI 스마트 체중계",
            "price": 45000,
            "rating": 4.3,
            "review_count": 800,
            "min_price": 45000,
            "max_price": 45000,
            "shipping_method": "일반배송",
            "delivery_days": 3
        }
    ]
    
    for prod in competitor_products:
        await storage.create("competitor_products", prod)
    
    # 키워드 데이터
    keyword_daily_data = []
    keywords = ["블루투스 이어폰", "스마트 체중계", "미니 가습기"]
    
    for keyword in keywords:
        for i in range(30):
            date = datetime.now() - timedelta(days=i)
            volume = 10000 - (i * 100)  # 하락 트렌드
            
            keyword_daily_data.append({
                "keyword": keyword,
                "date": date,
                "volume": volume
            })
    
    for data in keyword_daily_data:
        await storage.create("keyword_daily_data", data)
    
    return storage


class TestSalesAnalyzer:
    """판매 분석기 테스트"""
    
    @pytest.mark.asyncio
    async def test_analyze_product_sales(self, setup_test_data):
        """상품별 판매 분석 테스트"""
        storage = setup_test_data
        analyzer = SalesAnalyzer(storage)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        metrics = await analyzer.analyze_product_sales("1", start_date, end_date)
        
        assert isinstance(metrics, SalesMetrics)
        assert metrics.total_sales == 60  # 30일 * 2개
        assert metrics.total_revenue == Decimal("1794000")  # 30일 * 59800
        assert metrics.average_price == Decimal("29900")
    
    @pytest.mark.asyncio
    async def test_analyze_category_sales(self, setup_test_data):
        """카테고리별 판매 분석 테스트"""
        storage = setup_test_data
        analyzer = SalesAnalyzer(storage)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        result = await analyzer.analyze_category_sales("전자제품", start_date, end_date)
        
        assert result["category"] == "전자제품"
        assert result["total_products"] == 1
        assert result["total_sales"] == 60
    
    @pytest.mark.asyncio
    async def test_detect_trends(self, setup_test_data):
        """트렌드 감지 테스트"""
        storage = setup_test_data
        analyzer = SalesAnalyzer(storage, {"env": "test"})
        
        trends = await analyzer.detect_trends(lookback_days=30)
        
        assert isinstance(trends, list)
        # 테스트 데이터가 단순하므로 강한 트렌드는 없을 수 있음
    
    @pytest.mark.asyncio
    async def test_calculate_seasonality(self, setup_test_data):
        """계절성 분석 테스트"""
        storage = setup_test_data
        analyzer = SalesAnalyzer(storage)
        
        seasonality = await analyzer.calculate_seasonality("1")
        
        assert isinstance(seasonality, dict)
        assert len(seasonality) == 12  # 12개월
        assert all(isinstance(v, float) for v in seasonality.values())


class TestCompetitorMonitor:
    """경쟁사 모니터 테스트"""
    
    @pytest.mark.asyncio
    async def test_identify_competitors(self, setup_test_data):
        """경쟁사 식별 테스트"""
        storage = setup_test_data
        monitor = CompetitorMonitor(storage)
        
        competitors = await monitor.identify_competitors("1")
        
        assert isinstance(competitors, list)
        assert all(isinstance(c, CompetitorInfo) for c in competitors)
        
        if competitors:
            comp = competitors[0]
            assert comp.marketplace in ["coupang", "11st", "gmarket", "smartstore"]
    
    @pytest.mark.asyncio
    async def test_monitor_competitor_prices(self, setup_test_data):
        """경쟁사 가격 모니터링 테스트"""
        storage = setup_test_data
        monitor = CompetitorMonitor(storage)
        
        # 먼저 경쟁사 식별
        competitors = await monitor.identify_competitors("1")
        
        if competitors:
            result = await monitor.monitor_competitor_prices("1", competitors[:3])
            
            assert "product_id" in result
            assert "our_price" in result
            assert "price_statistics" in result
            assert "position" in result
    
    @pytest.mark.asyncio
    async def test_analyze_competitor_strategy(self, setup_test_data):
        """경쟁사 전략 분석 테스트"""
        storage = setup_test_data
        monitor = CompetitorMonitor(storage)
        
        # 테스트용 경쟁사 생성
        comp_info = CompetitorInfo(
            competitor_id="COMP001",
            name="테크샵",
            marketplace="coupang",
            product_count=50,
            average_rating=4.5,
            review_count=1200,
            min_price=Decimal("10000"),
            max_price=Decimal("100000"),
            average_price=Decimal("35000"),
            shipping_method="로켓배송",
            average_delivery_days=1,
            last_updated=datetime.now()
        )
        
        # 경쟁사 정보 저장
        await storage.create("competitors", comp_info.dict())
        
        result = await monitor.analyze_competitor_strategy("COMP001")
        
        assert "competitor_id" in result
        assert "portfolio" in result
        assert "pricing_strategy" in result
        assert "swot_analysis" in result


class TestKeywordResearcher:
    """키워드 연구자 테스트"""
    
    @pytest.mark.asyncio
    async def test_research_keyword(self, setup_test_data):
        """키워드 연구 테스트"""
        storage = setup_test_data
        researcher = KeywordResearcher(storage, {"env": "test"})
        
        metrics = await researcher.research_keyword("블루투스 이어폰", "전자제품")
        
        assert isinstance(metrics, KeywordMetrics)
        assert metrics.keyword == "블루투스 이어폰"
        assert metrics.category == "전자제품"
        assert metrics.search_volume > 0
        assert metrics.competition_level in ["low", "medium", "high"]
    
    @pytest.mark.asyncio
    async def test_find_opportunity_keywords(self, setup_test_data):
        """기회 키워드 발굴 테스트"""
        storage = setup_test_data
        researcher = KeywordResearcher(storage, {"env": "test"})
        
        opportunities = await researcher.find_opportunity_keywords(
            "전자제품",
            min_volume=100,
            max_competition="medium"
        )
        
        assert isinstance(opportunities, list)
        
        if opportunities:
            opp = opportunities[0]
            assert "keyword" in opp
            assert "metrics" in opp
            assert "opportunity_score" in opp
    
    @pytest.mark.asyncio
    async def test_analyze_keyword_combinations(self, setup_test_data):
        """키워드 조합 분석 테스트"""
        storage = setup_test_data
        researcher = KeywordResearcher(storage, {"env": "test"})
        
        base_keywords = ["무선", "블루투스", "이어폰"]
        combinations = await researcher.analyze_keyword_combinations(base_keywords)
        
        assert isinstance(combinations, list)
        
        if combinations:
            combo = combinations[0]
            assert "combination" in combo
            assert "keywords" in combo
            assert "synergy_score" in combo
    
    @pytest.mark.asyncio
    async def test_track_keyword_trends(self, setup_test_data):
        """키워드 트렌드 추적 테스트"""
        storage = setup_test_data
        researcher = KeywordResearcher(storage)
        
        keywords = ["블루투스 이어폰"]
        result = await researcher.track_keyword_trends(keywords, days=30)
        
        assert "keyword_trends" in result
        assert "summary" in result
        
        if keywords[0] in result["keyword_trends"]:
            trend_data = result["keyword_trends"][keywords[0]]
            assert "current_volume" in trend_data
            assert "trend" in trend_data


class TestTrendPredictor:
    """트렌드 예측기 테스트"""
    
    @pytest.mark.asyncio
    async def test_predict_trends(self, setup_test_data):
        """트렌드 예측 테스트"""
        storage = setup_test_data
        predictor = TrendPredictor(storage)
        
        trends = await predictor.predict_trends(horizon_days=30)
        
        assert isinstance(trends, list)
        assert all(isinstance(t, MarketTrend) for t in trends)
        
        if trends:
            trend = trends[0]
            assert trend.category
            assert trend.strength >= 0
            assert trend.direction in [TrendDirection.UP, TrendDirection.DOWN, TrendDirection.STABLE]
    
    @pytest.mark.asyncio
    async def test_predict_product_performance(self, setup_test_data):
        """상품 성과 예측 테스트"""
        storage = setup_test_data
        predictor = TrendPredictor(storage)
        
        result = await predictor.predict_product_performance("1", horizon_days=30)
        
        if "error" not in result:
            assert "product_id" in result
            assert "forecast" in result
            assert "confidence" in result
            assert "risks" in result
            assert "recommendations" in result
    
    @pytest.mark.asyncio
    async def test_identify_emerging_trends(self, setup_test_data):
        """신흥 트렌드 식별 테스트"""
        storage = setup_test_data
        predictor = TrendPredictor(storage)
        
        emerging = await predictor.identify_emerging_trends(min_growth_rate=10)
        
        assert isinstance(emerging, list)
        
        if emerging:
            trend = emerging[0]
            assert "type" in trend
            assert "growth_rate" in trend
            assert "risk_level" in trend


class TestSourcingDashboard:
    """소싱 대시보드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_overview(self, setup_test_data):
        """대시보드 개요 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        overview = await dashboard.get_overview()
        
        assert "summary" in overview
        assert "sales_performance" in overview
        assert "market_trends" in overview
        assert "opportunities" in overview
        assert "competition" in overview
        assert "keywords" in overview
        assert "alerts" in overview
    
    @pytest.mark.asyncio
    async def test_get_sales_dashboard(self, setup_test_data):
        """판매 대시보드 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        result = await dashboard.get_sales_dashboard(period_days=30)
        
        assert "period" in result
        assert "daily_trend" in result
        assert "categories" in result
        assert "products" in result
        assert "patterns" in result
        assert "customers" in result
        assert "insights" in result
    
    @pytest.mark.asyncio
    async def test_get_competition_dashboard(self, setup_test_data):
        """경쟁 분석 대시보드 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        result = await dashboard.get_competition_dashboard()
        
        assert "top_competitors" in result
        assert "price_analysis" in result
        assert "strategies" in result
        assert "positioning" in result
        assert "threats_opportunities" in result
        assert "recommendations" in result
    
    @pytest.mark.asyncio
    async def test_get_keyword_dashboard(self, setup_test_data):
        """키워드 분석 대시보드 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        result = await dashboard.get_keyword_dashboard()
        
        assert "trending" in result
        assert "opportunities" in result
        assert "performance" in result
        assert "combinations" in result
        assert "seasonal" in result
        assert "insights" in result
    
    @pytest.mark.asyncio
    async def test_get_trend_dashboard(self, setup_test_data):
        """트렌드 예측 대시보드 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        result = await dashboard.get_trend_dashboard()
        
        assert "market_trends" in result
        assert "emerging" in result
        assert "forecasts" in result
        assert "risks" in result
        assert "action_items" in result
    
    @pytest.mark.asyncio
    async def test_generate_report(self, setup_test_data):
        """리포트 생성 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        report = await dashboard.generate_report(report_type="weekly")
        
        assert isinstance(report, SourcingReport)
        assert report.report_type == "weekly"
        assert report.title
        assert report.summary
        assert report.key_findings
        assert report.recommendations
    
    @pytest.mark.asyncio
    async def test_export_dashboard_data(self, setup_test_data):
        """대시보드 데이터 내보내기 테스트"""
        storage = setup_test_data
        dashboard = SourcingDashboard(storage)
        
        # JSON 내보내기
        json_data = await dashboard.export_dashboard_data(
            dashboard_type="overview",
            format="json"
        )
        
        assert isinstance(json_data, str)
        assert len(json_data) > 0
        
        # CSV 내보내기
        csv_data = await dashboard.export_dashboard_data(
            dashboard_type="overview",
            format="csv"
        )
        
        assert isinstance(csv_data, str)


class TestIntegration:
    """통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_full_analysis_flow(self, setup_test_data):
        """전체 분석 플로우 테스트"""
        storage = setup_test_data
        
        # 1. 판매 분석
        sales_analyzer = SalesAnalyzer(storage)
        sales_metrics = await sales_analyzer.analyze_product_sales(
            "1",
            datetime.now() - timedelta(days=30),
            datetime.now()
        )
        
        assert sales_metrics.total_sales > 0
        
        # 2. 경쟁사 분석
        competitor_monitor = CompetitorMonitor(storage)
        competitors = await competitor_monitor.identify_competitors("1")
        
        # 3. 키워드 분석
        keyword_researcher = KeywordResearcher(storage, {"env": "test"})
        keyword_metrics = await keyword_researcher.research_keyword(
            "블루투스 이어폰"
        )
        
        assert keyword_metrics.search_volume > 0
        
        # 4. 트렌드 예측
        trend_predictor = TrendPredictor(storage)
        trends = await trend_predictor.predict_trends()
        
        # 5. 대시보드 생성
        dashboard = SourcingDashboard(storage)
        overview = await dashboard.get_overview()
        
        assert "summary" in overview
        assert overview["summary"]["total_revenue"] >= 0
    
    @pytest.mark.asyncio
    async def test_opportunity_discovery_flow(self, setup_test_data):
        """기회 발굴 플로우 테스트"""
        storage = setup_test_data
        
        # 1. 키워드 기회 찾기
        keyword_researcher = KeywordResearcher(storage, {"env": "test"})
        keyword_opportunities = await keyword_researcher.find_opportunity_keywords(
            "전자제품"
        )
        
        # 2. 트렌드 기반 기회
        trend_predictor = TrendPredictor(storage)
        emerging_trends = await trend_predictor.identify_emerging_trends()
        
        # 3. 대시보드에서 종합
        dashboard = SourcingDashboard(storage)
        overview = await dashboard.get_overview()
        
        assert "opportunities" in overview
        
        # 4. 리포트 생성
        report = await dashboard.generate_report(
            report_type="weekly",
            categories=["전자제품"]
        )
        
        assert report.opportunities is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])