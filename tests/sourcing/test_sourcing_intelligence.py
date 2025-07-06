"""
소싱 인텔리전스 시스템 통합 테스트
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

from dropshipping.models.sourcing import (
    CompetitorInfo,
    KeywordMetrics,
    MarketTrend,
    SalesMetrics,
    SourcingReport,
    TrendDirection,
)
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.dashboard import SourcingDashboard
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.sourcing.trend_predictor import TrendPredictor
from dropshipping.storage.base import BaseStorage
from dropshipping.models.product import StandardProduct


class MockStorage(BaseStorage):
    """테스트용 비동기식 Mock Storage"""

    def __init__(self):
        super().__init__()
        self.data = {
            "raw_products": {},
            "products": {},
            "sales": {},
            "keywords": {},
            "trends": {},
            "competitors": {},
            "suppliers": {},
            "marketplaces": {},
            "uploads": {},
            "sync_times": {},
        }
        self.id_counter = 1

    async def _create(self, table: str, data: dict) -> dict:
        if table not in self.data:
            self.data[table] = {}
        
        record_id = data.get("id", str(self.id_counter))
        if "id" not in data:
            self.id_counter += 1

        data["id"] = record_id
        data["created_at"] = datetime.now()
        data["updated_at"] = datetime.now()
        self.data[table][record_id] = data
        return data

    async def _list(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        if table not in self.data:
            return []

        items = sorted(list(self.data[table].values()), key=lambda x: x.get('id', ''))

        if filters:
            active_filters = {k: v for k, v in filters.items() if v is not None}
            if active_filters:
                truly_filtered_items = []
                for item in items:
                    match = True
                    for key, value in active_filters.items():
                        if key.endswith("_gte"):
                            field = key[:-4]
                            item_value = item.get(field)
                            if not (item_value and item_value >= value):
                                match = False
                                break
                        elif key.endswith("_lte"):
                            field = key[:-4]
                            item_value = item.get(field)
                            if not (item_value and item_value <= value):
                                match = False
                                break
                        else:
                            if item.get(key) != value:
                                match = False
                                break
                    if match:
                        truly_filtered_items.append(item)
                items = truly_filtered_items

        if offset > 0:
            items = items[offset:]
        if limit is not None:
            items = items[:limit]

        return items

    async def list(self, table: str, filters: Optional[Dict[str, Any]] = None, **kwargs) -> List[Dict[str, Any]]:
        """Public list method for compatibility with application code."""
        query_filters = filters.copy() if filters is not None else {}
        
        limit = kwargs.pop('limit', None)
        offset = kwargs.pop('offset', 0)
        
        # The rest of kwargs are assumed to be filters
        query_filters.update(kwargs)
        
        if not query_filters:
            query_filters = None

        return await self._list(table, query_filters, limit, offset)

    async def create(self, table: str, data: dict) -> dict:
        """Public create method."""
        return await self._create(table, data)

    async def save(self, table: str, data: dict) -> dict:
        """Public save method (alias for create in this mock)."""
        return await self._create(table, data)

    async def get(self, table: str, record_id: str) -> Optional[dict]:
        """Public get method."""
        if table in self.data and record_id in self.data[table]:
            return self.data[table][record_id]
        return None

    async def update(self, table: str, record_id: str, data: dict) -> bool:
        """Public update method."""
        if table in self.data and record_id in self.data[table]:
            self.data[table][record_id].update(data)
            self.data[table][record_id]['updated_at'] = datetime.now()
            return True
        return False

    # BaseStorage 추상 메서드 구현
    async def save_raw_product(self, raw_data: Dict[str, Any]) -> str:
        record = await self._create("raw_products", raw_data)
        return record["id"]

    async def save_processed_product(self, raw_id: str, product: StandardProduct) -> str:
        product_dict = product.model_dump()
        product_dict["raw_id"] = raw_id
        product_dict.setdefault("status", "active")  # Ensure products have a status
        record = await self._create("products", product_dict)
        return record["id"]

    async def exists_by_hash(self, supplier_id: str, data_hash: str) -> bool:
        products = await self._list("raw_products", filters={"supplier_id": supplier_id})
        return any(p.get("data_hash") == data_hash for p in products)

    async def get_product_by_supplier_id(self, supplier_id: str, supplier_product_id: str) -> Optional[StandardProduct]:
        products = await self._list("products", filters={"supplier_id": supplier_id, "supplier_product_id": supplier_product_id})
        if products:
            return StandardProduct(**products[0])
        return None
    
    async def get_all_products(self, limit: int = 1000, offset: int = 0) -> List[StandardProduct]:
        all_products_data = list(self.data["products"].values())[offset:offset+limit]
        return [StandardProduct(**data) for data in all_products_data]

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> bool:
        if product_id in self.data["products"]:
            self.data["products"][product_id].update(data)
            return True
        return False

    async def delete_product(self, product_id: str) -> bool:
        if product_id in self.data["products"]:
            del self.data["products"][product_id]
            return True
        return False

    async def get_sales_data(
        self,
        start_date: datetime,
        end_date: datetime,
        product_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters = {"sale_date_gte": start_date, "sale_date_lte": end_date}
        if product_id:
            filters["product_id"] = product_id
        return await self._list("sales", filters=filters)

    async def get_keyword_data(self, keyword: str) -> List[Dict[str, Any]]:
        return await self._list("keywords", filters={"keyword": keyword})

    async def get_trend_data(self, topic: str) -> List[Dict[str, Any]]:
        return await self._list("trends", filters={"topic": topic})

    async def get_competitor_data(self, product_id: str) -> List[Dict[str, Any]]:
        return await self._list("competitors", filters={"product_id": product_id})

    async def get_product_by_id(self, product_id: str) -> Optional[StandardProduct]:
        product_data = self.data["products"].get(product_id)
        if product_data:
            return StandardProduct(**product_data)
        return None

    async def get_products_by_category(self, category_code: str) -> List[StandardProduct]:
        products = await self._list("products", filters={"category_code": category_code})
        return [StandardProduct(**p) for p in products]

    async def get_products_by_supplier(self, supplier_id: str) -> List[StandardProduct]:
        products = await self._list("products", filters={"supplier_id": supplier_id})
        return [StandardProduct(**p) for p in products]

    async def get_all_suppliers(self) -> List[Dict[str, Any]]:
        return await self._list("suppliers")

    async def get_supplier_by_id(self, supplier_id: str) -> Optional[Dict[str, Any]]:
        return self.data["suppliers"].get(supplier_id)

    async def get_all_marketplaces(self) -> List[Dict[str, Any]]:
        return await self._list("marketplaces")

    async def get_marketplace_by_id(self, marketplace_id: str) -> Optional[Dict[str, Any]]:
        return self.data["marketplaces"].get(marketplace_id)

    async def get_uploads_by_product_id(self, product_id: str) -> List[Dict[str, Any]]:
        return await self._list("uploads", filters={"product_id": product_id})

    async def get_uploads_by_marketplace_id(self, marketplace_id: str) -> List[Dict[str, Any]]:
        return await self._list("uploads", filters={"marketplace_id": marketplace_id})

    async def log_upload_attempt(self, product_id: str, marketplace_id: str, success: bool, details: Optional[str] = None) -> None:
        pass

    async def get_last_sync_time(self, sync_type: str) -> Optional[datetime]:
        return self.data["sync_times"].get(sync_type)

    async def update_last_sync_time(self, sync_type: str, sync_time: datetime) -> None:
        self.data["sync_times"][sync_type] = sync_time

    async def get_raw_product(self, record_id: str) -> Optional[Dict[str, Any]]:
        return self.data["raw_products"].get(record_id)

    async def get_processed_product(self, record_id: str) -> Optional[StandardProduct]:
        product_data = self.data["products"].get(record_id)
        if product_data:
            return StandardProduct(**product_data)
        return None

    async def list_raw_products(
        self,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filters = {"supplier_id": supplier_id, "status": status}
        return await self._list("raw_products", filters=filters, limit=limit, offset=offset)

    async def update_status(self, record_id: str, status: str) -> bool:
        if record_id in self.data["raw_products"]:
            self.data["raw_products"][record_id]["status"] = status
            return True
        if record_id in self.data["products"]:
            self.data["products"][record_id]["status"] = status
            return True
        return False

    async def get_stats(self, supplier_id: Optional[str] = None) -> Dict[str, Any]:
        return {"raw": len(self.data["raw_products"]), "processed": len(self.data["products"])}

    async def upsert(
        self, table_name: str, records: List[Dict[str, Any]], on_conflict: str
    ) -> List[Dict[str, Any]]:
        # This is a simplified mock implementation
        results = []
        for record in records:
            # Assuming 'id' is the conflict key
            record_id = record.get("id")
            if record_id and record_id in self.data.get(table_name, {}):
                self.data[table_name][record_id].update(record)
                results.append(self.data[table_name][record_id])
            else:
                created_record = await self._create(table_name, record)
                results.append(created_record)
        return results

    async def get_marketplace_upload(self, product_id: str, marketplace: str) -> Optional[Dict[str, Any]]:
        uploads = await self._list("uploads", filters={"product_id": product_id, "marketplace_id": marketplace})
        if uploads:
            return uploads[0]
        return None

    async def save_marketplace_upload(self, record: Dict[str, Any]):
        await self._create("uploads", record)

    async def get_pricing_rules(self, active_only: bool = True) -> List[Dict[str, Any]]:
        return []

    async def get_supplier_code(self, supplier_name: str) -> Optional[str]:
        return "S001"

    async def get_marketplace_code(self, marketplace_name: str) -> Optional[str]:
        return "M001"

    async def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        return self.data.get("category_mappings", [])

    async def get_competitor_products(self, product_id: str) -> List[Dict[str, Any]]:
        """경쟁사 상품 정보 조회 (목업)"""
        return await self._list("competitors", filters={"product_id": product_id})

@pytest.fixture
def storage():
    return MockStorage()


@pytest.fixture
async def setup_test_data(storage: MockStorage):
    """테스트 데이터 설정"""
    products_data = [
        {"id": "1", "name": "스마트폰 거치대", "price": Decimal("15000"), "stock": 100, "status": "active", "cost": Decimal("7000"), "category_code": "액세서리", "supplier_id": "s1", "supplier_product_id": "p1"},
        {"id": "2", "name": "블루투스 이어폰", "price": Decimal("80000"), "stock": 50, "status": "active", "cost": Decimal("40000"), "category_code": "음향기기", "supplier_id": "s1", "supplier_product_id": "p2"},
        {"id": "3", "name": "휴대용 선풍기", "price": Decimal("25000"), "stock": 200, "status": "inactive", "cost": Decimal("12000"), "category_code": "계절가전", "supplier_id": "s2", "supplier_product_id": "p3"},
    ]
    products = [StandardProduct(**p) for p in products_data]
    for product in products:
        await storage.save_processed_product(raw_id=f"raw_{product.id}", product=product)

    # 주문 데이터 생성 (SalesAnalyzer가 orders 테이블을 사용함)
    orders_data = []
    for i in range(30):
        product = products[i % len(products)]
        order_date = datetime.now() - timedelta(days=i)
        orders_data.append({
            "id": f"order{i}",
            "marketplace": "test_market", 
            "marketplace_order_id": f"M{i}",
            "order_date": order_date,
            "status": "delivered" if i % 2 == 0 else "shipped",
            "items": [{
                "product_id": product.id,
                "quantity": (i % 5) + 1,
                "unit_price": product.price,
                "total_price": product.price * ((i % 5) + 1)
            }],
            "customer": {"name": f"Customer{i}"},
            "payment": {"total_amount": product.price * ((i % 5) + 1)},
            "delivery": {"status": "delivered" if i % 2 == 0 else "in_transit"}
        })
    await storage.upsert("orders", orders_data, on_conflict="id")

    trends_data = [
        {"id": "t1", "topic": "홈트레이닝", "monthly_searches": 50000, "trend_date": datetime.now() - timedelta(days=5)},
    ]
    await storage.upsert("trends", trends_data, on_conflict="id")

    competitors_data = [
        {"id": "c1", "product_id": "1", "name": "타사 거치대", "price": 14000, "reviews": 50, "rating": 4.1},
        {"id": "c2", "product_id": "1", "name": "또다른 거치대", "price": 16000, "reviews": 150, "rating": 4.4},
    ]
    await storage.upsert("competitors", competitors_data, on_conflict="id")
    
    return storage



class TestSalesAnalyzer:
    """판매 분석기 테스트"""

    @pytest.mark.asyncio
    async def test_analyze_product_sales(self, storage, setup_test_data):
        """상품 판매 분석 테스트"""
        analyzer = SalesAnalyzer(storage)
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        metrics = await analyzer.analyze_product_sales("1", start_date, end_date)
        assert metrics.total_sales > 0

    @pytest.mark.asyncio
    async def test_analyze_category_sales(self, storage, setup_test_data):
        """카테고리 판매 분석 테스트"""
        analyzer = SalesAnalyzer(storage)
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        metrics = await analyzer.analyze_category_sales("액세서리", start_date, end_date)
        assert metrics["total_sales"] > 0

    @pytest.mark.asyncio
    async def test_detect_trends(self, storage, setup_test_data):
        """트렌드 감지 테스트"""
        analyzer = SalesAnalyzer(storage)
        trends = await analyzer.detect_trends()
        assert trends is not None

    @pytest.mark.asyncio
    async def test_calculate_seasonality(self, storage, setup_test_data):
        """계절성 분석 테스트"""
        analyzer = SalesAnalyzer(storage)
        seasonality = await analyzer.calculate_seasonality(product_id="1")
        assert isinstance(seasonality, dict)
        assert "1" in seasonality  # Check for product-specific seasonality


class TestCompetitorMonitor:
    """경쟁사 모니터 테스트"""

    @pytest.mark.asyncio
    async def test_identify_competitors(self, storage, setup_test_data):
        """경쟁사 식별 테스트"""
        monitor = CompetitorMonitor(storage)
        competitors = await monitor.identify_competitors("1")
        assert isinstance(competitors, list)
        assert len(competitors) > 0

    @pytest.mark.asyncio
    async def test_monitor_competitor_prices(self, storage, setup_test_data):
        """경쟁사 가격 모니터링 테스트"""
        monitor = CompetitorMonitor(storage)
        price_analysis = await monitor.monitor_competitor_prices("1")
        assert isinstance(price_analysis, list)

    @pytest.mark.asyncio
    async def test_analyze_competitor_strategy(self, storage, setup_test_data):
        """경쟁사 전략 분석 테스트"""
        monitor = CompetitorMonitor(storage)
        strategy = await monitor.analyze_competitor_strategy("1")
        assert isinstance(strategy, dict)


class TestKeywordResearcher:
    """키워드 연구자 테스트"""

    @pytest.mark.asyncio
    async def test_research_keyword(self, storage, setup_test_data):
        """키워드 연구 테스트"""
        researcher = KeywordResearcher(storage, {"env": "test"})
        keyword = await researcher.research_keyword("블루투스 이어폰")
        assert isinstance(keyword, KeywordMetrics)
        assert keyword.keyword == "블루투스 이어폰"

    @pytest.mark.asyncio
    async def test_find_opportunity_keywords(self, storage, setup_test_data):
        """기회 키워드 발굴 테스트"""
        researcher = KeywordResearcher(storage, {"env": "test"})
        opportunities = await researcher.find_opportunity_keywords("전자제품")
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_analyze_keyword_combinations(self, storage, setup_test_data):
        """키워드 조합 분석 테스트"""
        researcher = KeywordResearcher(storage, {"env": "test"})
        combinations = await researcher.analyze_keyword_combinations(
            ["무선", "블루투스", "이어폰"]
        )
        assert isinstance(combinations, list)

    @pytest.mark.asyncio
    async def test_track_keyword_trends(self, storage, setup_test_data):
        """키워드 트렌드 추적 테스트"""
        researcher = KeywordResearcher(storage, {"env": "test"})
        trends = await researcher.track_keyword_trends("무선 이어폰")
        assert trends is not None


class TestTrendPredictor:
    """트렌드 예측기 테스트"""

    @pytest.mark.asyncio
    async def test_predict_trends(self, storage, setup_test_data):
        """트렌드 예측 테스트"""
        predictor = TrendPredictor(storage)
        trends = await predictor.predict_trends("홈트레이닝")  # Use topic from test data
        assert len(trends) > 0

    @pytest.mark.asyncio
    async def test_predict_product_performance(self, storage, setup_test_data):
        """상품 성과 예측 테스트"""
        predictor = TrendPredictor(storage)
        performance = await predictor.predict_product_performance("3")
        assert "confidence" in performance
        assert performance["confidence"] >= 0

    @pytest.mark.asyncio
    async def test_identify_emerging_trends(self, storage, setup_test_data):
        """신흥 트렌드 식별 테스트"""
        predictor = TrendPredictor(storage)
        emerging = await predictor.identify_emerging_trends()
        assert isinstance(emerging, list)
        assert len(emerging) > 0


class TestSourcingDashboard:
    """소싱 대시보드 테스트"""

    @pytest.mark.asyncio
    async def test_get_overview(self, storage, setup_test_data):
        """대시보드 개요 테스트"""
        dashboard = SourcingDashboard(storage)
        overview = await dashboard.get_overview()
        assert "summary" in overview

    @pytest.mark.asyncio
    async def test_get_sales_dashboard(self, storage, setup_test_data):
        """판매 대시보드 테스트"""
        dashboard = SourcingDashboard(storage)
        sales_dash = await dashboard.get_sales_dashboard()
        assert "period" in sales_dash

    @pytest.mark.asyncio
    async def test_get_competition_dashboard(self, storage, setup_test_data):
        """경쟁 분석 대시보드 테스트"""
        dashboard = SourcingDashboard(storage)
        comp_dash = await dashboard.get_competition_dashboard()
        assert "top_competitors" in comp_dash

    @pytest.mark.asyncio
    async def test_get_keyword_dashboard(self, storage, setup_test_data):
        """키워드 분석 대시보드 테스트"""
        dashboard = SourcingDashboard(storage)
        key_dash = await dashboard.get_keyword_dashboard()
        assert "trending" in key_dash

    @pytest.mark.asyncio
    async def test_get_trend_dashboard(self, storage, setup_test_data):
        """트렌드 예측 대시보드 테스트"""
        dashboard = SourcingDashboard(storage)
        trend_dash = await dashboard.get_trend_dashboard()
        assert "market_trends" in trend_dash

    @pytest.mark.asyncio
    async def test_generate_report(self, storage, setup_test_data):
        """리포트 생성 테스트"""
        dashboard = SourcingDashboard(storage)
        report = await dashboard.generate_report()
        assert isinstance(report, SourcingReport)
        assert report.title

    @pytest.mark.asyncio
    async def test_export_dashboard_data(self, storage, setup_test_data):
        """대시보드 데이터 내보내기 테스트"""
        dashboard = SourcingDashboard(storage)
        data = await dashboard.export_dashboard_data("sales", "csv")
        assert isinstance(data, str)


class TestIntegration:
    """통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_analysis_flow(self, storage, setup_test_data):
        """전체 분석 플로우 테스트"""
        # 1. 판매 분석
        sales_analyzer = SalesAnalyzer(storage)
        sales_metrics = await sales_analyzer.analyze_product_sales(
            "1", datetime.now() - timedelta(days=30), datetime.now()
        )
        assert sales_metrics.total_sales > 0

        # 2. 경쟁사 분석
        competitor_monitor = CompetitorMonitor(storage)
        await competitor_monitor.identify_competitors("1")

        # 3. 키워드 분석
        keyword_researcher = KeywordResearcher(storage, {"env": "test"})
        keyword_metrics = await keyword_researcher.research_keyword("블루투스 이어폰")
        assert keyword_metrics.search_volume >= 0

        # 4. 트렌드 예측
        trend_predictor = TrendPredictor(storage)
        await trend_predictor.predict_trends()

        # 5. 대시보드 생성
        dashboard = SourcingDashboard(storage)
        overview = await dashboard.get_overview()
        assert "summary" in overview
        assert overview["summary"]["total_revenue"] >= 0

    @pytest.mark.asyncio
    async def test_opportunity_discovery_flow(self, storage, setup_test_data):
        """기회 발굴 플로우 테스트"""
        # 1. 키워드 기회 찾기
        keyword_researcher = KeywordResearcher(storage, {"env": "test"})
        await keyword_researcher.find_opportunity_keywords("전자제품")

        # 2. 트렌드 기반 기회
        trend_predictor = TrendPredictor(storage)
        await trend_predictor.identify_emerging_trends()

        # 3. 대시보드에서 종합
        dashboard = SourcingDashboard(storage)
        overview = await dashboard.get_overview()
        assert "opportunities" in overview

        # 4. 리포트 생성
        report = await dashboard.generate_report(categories=["전자제품"])
        assert report is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
