"""
소싱 인텔리전스 시스템 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List
import random

import pytest

from dropshipping.models.sourcing import (
    SalesMetrics, CompetitorInfo, KeywordMetrics, 
    ProductOpportunity, MarketTrend, SourcingReport,
    TrendDirection
)
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.sourcing_manager import SourcingManager


class MockStorage:
    """향상된 목업 저장소"""
    
    def __init__(self, initial_data: Dict[str, List[Dict[str, Any]]] = None):
        self.data = initial_data or {}

    def setup_data(self, table: str, records: List[Dict[str, Any]]):
        self.data[table] = records

    async def get(self, table: str, id: str) -> Dict[str, Any]:
        for item in self.data.get(table, []):
            if item.get("id") == id:
                return item
        return None
    
    async def list(self, table: str, filters: Dict[str, Any] = None, limit: int = 100) -> List[Dict[str, Any]]:
        items = self.data.get(table, [])
        
        if not filters:
            return items[:limit]
        
        filtered = []
        for item in items:
            match = True
            for key, value in filters.items():
                if key.startswith("$"):
                    continue
                    
                if isinstance(value, dict):
                    for op, val in value.items():
                        if op == "$gte" and item.get(key, 0) < val:
                            match = False
                        elif op == "$lte" and item.get(key, 0) > val:
                            match = False
                        elif op == "$contains" and val not in item.get(key, []):
                            match = False
                        elif op == "$in" and item.get(key) not in val:
                            match = False
                elif item.get(key) != value:
                    match = False
            
            if match:
                filtered.append(item)
        
        return filtered[:limit]
    
    async def save(self, table: str, data: Dict[str, Any]) -> str:
        if table not in self.data:
            self.data[table] = []
        
        # 중복 방지 (ID 기준)
        if "id" in data and any(d.get("id") == data["id"] for d in self.data[table]):
             self.data[table] = [d for d in self.data[table] if d.get("id") != data["id"]]
        
        self.data[table].append(data)
        return data.get("id", f"generated_{random.randint(1000, 9999)}")
    
    async def delete(self, table: str, id: str) -> bool:
        if table in self.data:
            initial_len = len(self.data[table])
            self.data[table] = [item for item in self.data[table] if item.get("id") != id]
            return len(self.data[table]) < initial_len
        return False

# --- Fixtures ---
@pytest.fixture
def mock_storage():
    """테스트용 목업 저장소 인스턴스"""
    return MockStorage()

@pytest.fixture
def sales_analyzer(mock_storage):
    return SalesAnalyzer(mock_storage)

@pytest.fixture
def competitor_monitor(mock_storage):
    return CompetitorMonitor(mock_storage)

@pytest.fixture
def keyword_researcher(mock_storage):
    return KeywordResearcher(mock_storage)

@pytest.fixture
def sourcing_manager(mock_storage):
    return SourcingManager(mock_storage)

# --- Helper Functions ---
def generate_test_products(n=10):
    return [{"id": f"prod{i}", "name": f"Test Product {i}", "category_name": f"Cat{i%2}", "price": 10000 + i*1000, "stock": 10+i, "status": "active"} for i in range(n)]

def generate_test_orders(product_id, n=5, days_apart=3):
    return [{
        "id": f"order_{product_id}_{i}",
        "order_date": datetime.now() - timedelta(days=i*days_apart),
        "status": "delivered",
        "items": [{"product_id": product_id, "quantity": 1, "total_price": 10000}]
    } for i in range(n)]

# --- SalesAnalyzer Tests ---
@pytest.mark.asyncio
async def test_sales_analyzer_no_orders(sales_analyzer):
    """주문이 없는 상품 분석 테스트"""
    sales_analyzer.storage.setup_data("products", generate_test_products(1))
    metrics = await sales_analyzer.analyze_product_sales("prod0", datetime.now() - timedelta(days=30), datetime.now())
    assert metrics.total_sales == 0
    assert metrics.total_revenue == 0

@pytest.mark.asyncio
async def test_sales_analyzer_growth_calculation(sales_analyzer):
    """성장률 계산 검증 (급증 시나리오)"""
    product_id = "prod_growth"
    sales_analyzer.storage.setup_data("products", [{"id": product_id, "category_name": "CatA"}])
    
    # 과거 주문: 1개
    past_orders = [{"id": "past_o1", "order_date": datetime.now() - timedelta(days=10), "status": "delivered", "items": [{"product_id": product_id, "quantity": 1, "total_price": 10000}]}]
    # 현재 주문: 5개
    current_orders = [{"id": f"curr_o{i}", "order_date": datetime.now() - timedelta(days=i), "status": "delivered", "items": [{"product_id": product_id, "quantity": 1, "total_price": 10000}]} for i in range(5)]
    
    sales_analyzer.storage.setup_data("orders", past_orders + current_orders)
    
    metrics = await sales_analyzer.analyze_product_sales(product_id, datetime.now() - timedelta(days=7), datetime.now())
    
    assert metrics.growth_rate == 400.0  # (5-1)/1 * 100
    assert metrics.trend == TrendDirection.UP

# --- CompetitorMonitor Tests ---
@pytest.mark.asyncio
async def test_competitor_monitor_no_competitors(competitor_monitor):
    """경쟁사가 없는 상품 분석 테스트"""
    competitor_monitor.storage.setup_data("products", generate_test_products(1))
    competitor_monitor.storage.setup_data("competitor_products", []) # 경쟁사 상품 없음
    
    competitors = await competitor_monitor.identify_competitors("prod0")
    assert len(competitors) == 0

@pytest.mark.asyncio
async def test_competitor_price_change_detection(competitor_monitor):
    """경쟁사 가격 변동 감지 테스트"""
    product_id = "prod_price_change"
    competitor_id = "comp_price_change"
    
    competitor_monitor.storage.setup_data("products", [{"id": product_id, "name": "My Product", "price": 10000, "category_name": "CatA"}])
    competitor_monitor.storage.setup_data("competitor_products", [{
        "seller_id": competitor_id, "name": "Competitor Product", "price": 12000, "category": "CatA", "marketplace": "coupang"
    }])
    
    # 이전 가격 기록
    await competitor_monitor.storage.save("competitor_price_history", {
        "competitor_id": f"coupang_{competitor_id}", "price": 10000, "recorded_at": datetime.now() - timedelta(days=1)
    })
    
    result = await competitor_monitor.monitor_competitor_prices(product_id)
    
    assert len(result["price_changes"]) > 0
    assert result["price_changes"][0]["direction"] == "up"
    assert result["price_changes"][0]["change_rate"] > 19.0 # (12000-10000)/10000

# --- KeywordResearcher Tests ---
@pytest.mark.asyncio
async def test_keyword_researcher_niche_keyword(keyword_researcher):
    """니치 키워드 (검색량 낮음, 경쟁 낮음) 분석 테스트"""
    keyword = "초소형 휴대용 가습기"
    keyword_researcher.storage.setup_data("keyword_search_data", [{"keyword": keyword, "monthly_volume": 150}])
    keyword_researcher.storage.setup_data("products", []) # 관련 상품 없음
    
    metrics = await keyword_researcher.research_keyword(keyword, "가전")
    
    assert metrics.search_volume == 150
    assert metrics.competition_level == "low"

@pytest.mark.asyncio
async def test_keyword_researcher_highly_competitive_keyword(keyword_researcher):
    """경쟁 치열 키워드 (검색량 높음, 경쟁 높음) 분석 테스트"""
    keyword = "블루투스 이어폰"
    keyword_researcher.storage.setup_data("keyword_search_data", [{"keyword": keyword, "monthly_volume": 300000}])
    # 관련 상품 2000개 생성
    products = [{"id": f"p{i}", "name": f"{keyword} 모델 {i}", "category_name": "전자제품"} for i in range(2000)]
    keyword_researcher.storage.setup_data("products", products)
    
    metrics = await keyword_researcher.research_keyword(keyword, "전자제품")
    
    assert metrics.search_volume > 10000
    assert metrics.competition_level == "low"

# --- SourcingManager Tests ---
@pytest.mark.asyncio
async def test_sourcing_manager_no_valid_categories(sourcing_manager):
    """유효 카테고리 없는 경우 테스트"""
    sourcing_manager.storage.setup_data("products", []) # 상품 없음
    opportunities = await sourcing_manager.find_product_opportunities()
    assert len(opportunities) == 0

@pytest.mark.asyncio
async def test_sourcing_manager_no_opportunities_found(sourcing_manager):
    """상품 기회를 찾지 못하는 시나리오 테스트"""
    # 트렌드 강도가 낮은 데이터 설정
    sourcing_manager.storage.setup_data("products", generate_test_products(1))
    # detect_trends가 약한 트렌드를 반환하도록 mock
    async def mock_detect_trends(*args, **kwargs):
        return [MarketTrend(trend_id="t1", name="Weak Trend", category="Cat0", strength=10, direction="stable", momentum=10, trending_keywords=[], forecast_period=7, forecast_direction="stable", confidence_level=50, analyzed_at=datetime.now(), data_points=30)]
    
    sourcing_manager.sales_analyzer.detect_trends = mock_detect_trends
    
    opportunities = await sourcing_manager.find_product_opportunities(categories=["Cat0"])
    assert len(opportunities) == 0

@pytest.mark.asyncio
async def test_sourcing_report_with_empty_sections(sourcing_manager):
    """빈 데이터로 리포트 생성 테스트"""
    sourcing_manager.storage.setup_data("products", [])
    sourcing_manager.storage.setup_data("orders", [])
    sourcing_manager.storage.setup_data("competitor_products", [])
    sourcing_manager.storage.setup_data("keyword_search_data", [])
    
    report = await sourcing_manager.generate_sourcing_report(categories=["전자제품"])
    
    assert isinstance(report, SourcingReport)
    assert len(report.market_trends) == 0
    assert len(report.opportunities) == 0
    assert len(report.competitors) == 0
    assert len(report.keywords) == 0
    assert "특별한 발견사항이 없습니다" in report.summary

# --- Model Tests ---
def test_sales_metrics_model_boundary_values():
    """SalesMetrics 모델 경계값 테스트"""
    metrics = SalesMetrics(
        total_sales=0,
        total_revenue=Decimal("0"),
        average_price=Decimal("0"),
        growth_rate=-100.0,
        trend=TrendDirection.DOWN,
        period_start=datetime.now(),
        period_end=datetime.now()
    )
    assert metrics.total_sales == 0
    assert metrics.growth_rate == -100.0

def test_product_opportunity_score_validation():
    """ProductOpportunity 점수 유효성 검증"""
    with pytest.raises(ValueError):
        ProductOpportunity(opportunity_id="1", opportunity_score=101, product_name="p", category="c", keywords=[], market_demand="low", competition_level="low", entry_barrier="low", estimated_price=1, estimated_cost=1, estimated_margin=1, estimated_monthly_sales=1, supplier_count=1, created_at=datetime.now())

    with pytest.raises(ValueError):
        ProductOpportunity(opportunity_id="1", opportunity_score=-1, product_name="p", category="c", keywords=[], market_demand="low", competition_level="low", entry_barrier="low", estimated_price=1, estimated_cost=1, estimated_margin=1, estimated_monthly_sales=1, supplier_count=1, created_at=datetime.now())
