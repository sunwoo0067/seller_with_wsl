"""
소싱 인텔리전스 시스템 간단한 테스트
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.storage.base import BaseStorage


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
                        elif "$in" in value:
                            if item.get(key) not in value["$in"]:
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

    # BaseStorage 추상 메서드 구현
    async def save_raw_product(self, supplier: str, product_data: dict) -> dict:
        return await self.create("raw_products", product_data)

    async def save_processed_product(self, product_data: dict) -> dict:
        return await self.create("products", product_data)

    async def get_raw_product(self, supplier: str, product_id: str) -> dict:
        return await self.get(
            "raw_products", filters={"supplier": supplier, "product_id": product_id}
        )

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
            "failed": len([p for p in products if p.get("status") == "failed"]),
        }

    async def save(self, table: str, data: dict) -> dict:
        """save 메서드 (create의 별칭)"""
        return await self.create(table, data)

    # 추가 필수 메서드들
    async def get_all_category_mappings(self):
        """카테고리 매핑 조회"""
        return await self.list("category_mappings")

    async def get_marketplace_code(self, marketplace: str) -> Optional[str]:
        """마켓플레이스 코드 조회"""
        return marketplace.upper()

    async def get_marketplace_upload(self, product_id: str, marketplace: str) -> Optional[dict]:
        """마켓플레이스 업로드 정보 조회"""
        uploads = await self.list(
            "marketplace_uploads", filters={"product_id": product_id, "marketplace": marketplace}
        )
        return uploads[0] if uploads else None

    async def get_pricing_rules(self, supplier: str) -> list:
        """가격 규칙 조회"""
        return await self.list("pricing_rules", filters={"supplier": supplier})

    async def get_supplier_code(self, supplier: str) -> Optional[str]:
        """공급사 코드 조회"""
        return supplier.upper()

    async def save_marketplace_upload(self, upload_data: dict) -> dict:
        """마켓플레이스 업로드 정보 저장"""
        return await self.create("marketplace_uploads", upload_data)

    async def upsert(self, table: str, data: dict, unique_fields: list = None) -> dict:
        """업서트 (생성 또는 업데이트)"""
        if unique_fields:
            # unique_fields로 기존 데이터 찾기
            filters = {field: data.get(field) for field in unique_fields}
            existing = await self.list(table, filters=filters, limit=1)
            if existing:
                return await self.update(table, existing[0]["id"], data)
        return await self.create(table, data)


async def setup_test_data():
    """테스트 데이터 설정"""
    storage = MockStorage()

    # 상품 데이터
    products = [
        {
            "id": "1",
            "name": "무선 이어폰 블루투스 5.0",
            "category_name": "전자제품",
            "price": 29900,
            "stock": 100,
            "status": "active",
        },
        {
            "id": "2",
            "name": "스마트 체중계 블루투스 연동",
            "category_name": "헬스케어",
            "price": 39900,
            "stock": 50,
            "status": "active",
        },
    ]

    for product in products:
        await storage.create("products", product)

    # 주문 데이터
    for i in range(10):
        order_date = datetime.now() - timedelta(days=i)
        order = {
            "id": str(i + 1),
            "order_date": order_date,
            "status": "delivered",
            "items": [
                {"product_id": "1", "quantity": 2, "unit_price": 29900, "total_price": 59800}
            ],
            "customer": {"name": f"고객{i + 1}", "phone": f"010-1234-{5000 + i:04d}"},
        }
        await storage.create("orders", order)

    return storage


async def test_sales_analyzer():
    """판매 분석기 테스트"""
    print("=== 판매 분석기 테스트 ===")

    storage = await setup_test_data()
    analyzer = SalesAnalyzer(storage)

    # 상품 판매 분석
    end_date = datetime.now()
    start_date = end_date - timedelta(days=10)

    metrics = await analyzer.analyze_product_sales("1", start_date, end_date)

    print(f"총 판매량: {metrics.total_sales}")
    print(f"총 매출: {metrics.total_revenue}")
    print(f"평균 가격: {metrics.average_price}")
    print(f"성장률: {metrics.growth_rate}%")
    print(f"트렌드: {metrics.trend}")

    assert metrics.total_sales == 20  # 10일 * 2개
    assert metrics.total_revenue == Decimal("598000")  # 10일 * 59800

    print("✓ 판매 분석 테스트 통과")


async def test_competitor_monitor():
    """경쟁사 모니터 테스트"""
    print("\n=== 경쟁사 모니터 테스트 ===")

    storage = await setup_test_data()

    # 경쟁사 데이터 추가
    await storage.create(
        "competitor_products",
        {
            "seller_id": "COMP001",
            "seller_name": "테크샵",
            "marketplace": "coupang",
            "category": "전자제품",
            "name": "프리미엄 무선 이어폰",
            "price": 35000,
            "rating": 4.5,
            "review_count": 1200,
        },
    )

    monitor = CompetitorMonitor(storage)

    # 경쟁사 식별
    competitors = await monitor.identify_competitors("1")

    print(f"발견된 경쟁사 수: {len(competitors)}")

    if competitors:
        comp = competitors[0]
        print(f"경쟁사: {comp.name}")
        print(f"마켓플레이스: {comp.marketplace}")
        print(f"평균 가격: {comp.average_price}")

        # 가격 모니터링
        result = await monitor.monitor_competitor_prices("1", competitors[:1])

        print(f"\n우리 가격: {result['our_price']}")
        print(f"경쟁사 평균: {result['price_statistics']['avg']}")
        print(f"가격 경쟁력: {result['position']['competitiveness']}")

    print("✓ 경쟁사 모니터 테스트 통과")


async def test_keyword_researcher():
    """키워드 연구자 테스트"""
    print("\n=== 키워드 연구자 테스트 ===")

    storage = await setup_test_data()
    researcher = KeywordResearcher(storage, {"env": "test"})

    # 키워드 연구
    metrics = await researcher.research_keyword("블루투스 이어폰", "전자제품")

    print(f"키워드: {metrics.keyword}")
    print(f"월간 검색량: {metrics.search_volume:,}")
    print(f"경쟁도: {metrics.competition_level}")
    print(f"트렌드: {metrics.trend}")
    print(f"관련 상품 수: {metrics.product_count}")
    print(f"평균 가격: {metrics.average_price}")

    assert metrics.keyword == "블루투스 이어폰"
    assert metrics.search_volume > 0

    # 기회 키워드 찾기
    opportunities = await researcher.find_opportunity_keywords(
        "전자제품", min_volume=100, max_competition="medium"
    )

    print(f"\n발견된 기회 키워드: {len(opportunities)}개")

    print("✓ 키워드 연구 테스트 통과")


async def main():
    """메인 테스트 실행"""
    try:
        await test_sales_analyzer()
        await test_competitor_monitor()
        await test_keyword_researcher()

        print("\n=== 모든 테스트 통과! ===")

    except Exception as e:
        print(f"\n❌ 테스트 실패: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
