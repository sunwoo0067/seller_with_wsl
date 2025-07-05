"""
스케줄러 테스트
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from dropshipping.scheduler.base import (
    BaseJob, BaseScheduler, JobStatus, JobPriority
)
from dropshipping.scheduler.jobs import (
    DailyCollectionJob,
    InventoryUpdateJob,
    PriceAdjustmentJob,
    OrderSyncJob,
    ReportGenerationJob
)
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
                        # 특수 필터 처리
                        if "$in" in value:
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
    
    async def save(self, table: str, data: dict) -> dict:
        """save 메서드 (create의 별칭)"""
        return await self.create(table, data)


class TestJob(BaseJob):
    """테스트용 작업"""
    
    async def validate(self) -> bool:
        return True
    
    async def execute(self) -> dict:
        await asyncio.sleep(0.1)  # 작업 시뮬레이션
        return {"result": "success"}


async def test_base_job():
    """BaseJob 테스트"""
    storage = MockStorage()
    job = TestJob("test_job", storage)
    
    # 초기 상태
    assert job.name == "test_job"
    assert job.status == JobStatus.PENDING
    assert job.priority == JobPriority.NORMAL
    
    # 작업 실행
    result = await job.run()
    
    # 실행 후 상태
    assert job.status == JobStatus.COMPLETED
    assert result == {"result": "success"}
    assert job.start_time is not None
    assert job.end_time is not None
    assert job.get_duration() is not None
    
    # 작업 이력 확인
    history = await storage.list("job_history")
    assert len(history) > 0
    assert history[0]["name"] == "test_job"
    assert history[0]["status"] == "completed"


async def test_base_scheduler():
    """BaseScheduler 테스트"""
    storage = MockStorage()
    scheduler = BaseScheduler(storage)
    
    # 작업 등록
    scheduler.register_job("test_job", TestJob)
    assert "test_job" in scheduler.job_classes
    
    # 작업 추가
    with patch.object(scheduler.scheduler, 'add_job') as mock_add_job:
        job = scheduler.add_interval_job("test_job", seconds=10)
        mock_add_job.assert_called_once()
    
    # 통계 확인
    stats = scheduler.get_stats()
    assert stats["total_jobs"] == 0
    assert stats["completed_jobs"] == 0
    assert stats["failed_jobs"] == 0


async def test_daily_collection_job():
    """일일 수집 작업 테스트"""
    storage = MockStorage()
    
    # 테스트 데이터 설정
    await storage.create("suppliers", {"name": "domeme", "active": True})
    
    # Mock Fetcher/Transformer
    with patch('dropshipping.scheduler.jobs.collection_job.DomemeFetcher') as MockFetcher:
        with patch('dropshipping.scheduler.jobs.collection_job.DomemeTransformer') as MockTransformer:
            # Mock 설정
            mock_fetcher = Mock()
            mock_fetcher.fetch_products = Mock(return_value=[
                {"id": "1", "name": "테스트 상품 1"},
                {"id": "2", "name": "테스트 상품 2"}
            ])
            mock_fetcher.is_processed = Mock(return_value=False)
            mock_fetcher.mark_as_processed = Mock(return_value=None)
            MockFetcher.return_value = mock_fetcher
            
            mock_transformer = Mock()
            mock_transformer.transform = Mock(return_value=Mock(dict=lambda: {
                "id": "1",
                "name": "변환된 상품",
                "price": 10000
            }))
            MockTransformer.return_value = mock_transformer
            
            # 작업 실행
            job = DailyCollectionJob(storage, {
                "suppliers": ["domeme"],
                "process_ai": False
            })
            
            result = await job.run()
            
            # 검증
            assert job.status == JobStatus.COMPLETED
            assert job.stats["total_fetched"] == 2
            assert job.stats["total_processed"] == 2


async def test_inventory_update_job():
    """재고 업데이트 작업 테스트"""
    storage = MockStorage()
    
    # 테스트 상품 생성
    await storage.create("products", {
        "id": "1",
        "name": "테스트 상품",
        "supplier": "domeme",
        "supplier_product_id": "D001",
        "status": "active"
    })
    
    await storage.create("listings", {
        "product_id": "1",
        "marketplace": "coupang",
        "marketplace_product_id": "C001",
        "status": "active",
        "stock": 100
    })
    
    # Mock Fetcher/Uploader
    with patch('dropshipping.scheduler.jobs.inventory_update_job.DomemeFetcher') as MockFetcher:
        with patch('dropshipping.scheduler.jobs.inventory_update_job.CoupangUploader') as MockUploader:
            # Mock 설정
            mock_fetcher = Mock()
            mock_fetcher.get_stock = Mock(return_value=50)
            MockFetcher.return_value = mock_fetcher
            
            mock_uploader = Mock()
            mock_uploader.update_stock = Mock(return_value={"success": True})
            MockUploader.return_value = mock_uploader
            
            # 작업 실행
            job = InventoryUpdateJob(storage, {
                "suppliers": ["domeme"],
                "marketplaces": ["coupang"],
                "update_mode": "incremental"
            })
            
            # 변경된 상품 시뮬레이션
            await storage.create("inventory_changes", {
                "product_id": "1",
                "created_at": datetime.now()
            })
            
            result = await job.run()
            
            # 검증
            assert job.status == JobStatus.COMPLETED
            assert job.stats["total_checked"] == 1
            assert job.stats["total_updated"] == 1


async def test_price_adjustment_job():
    """가격 조정 작업 테스트"""
    storage = MockStorage()
    
    # 테스트 상품 생성
    await storage.create("products", {
        "id": "1",
        "name": "테스트 상품",
        "base_price": 10000,
        "current_price": 10000,
        "cost": 5000,
        "category_name": "전자제품",
        "status": "active"
    })
    
    await storage.create("listings", {
        "product_id": "1",
        "marketplace": "coupang",
        "marketplace_product_id": "C001",
        "price": 10000,
        "status": "active"
    })
    
    # 경쟁사 가격 변경 시뮬레이션
    await storage.create("competitor_price_changes", {
        "product_id": "1",
        "detected_at": datetime.now()
    })
    
    # Mock 설정
    with patch('dropshipping.scheduler.jobs.price_adjustment_job.CompetitorMonitor') as MockMonitor:
        with patch('dropshipping.scheduler.jobs.price_adjustment_job.CoupangUploader') as MockUploader:
            # 경쟁 모니터 Mock
            mock_monitor = Mock()
            mock_monitor.identify_competitors = Mock(return_value=[
                Mock(name="경쟁사1", marketplace="coupang", average_price=9500)
            ])
            mock_monitor.monitor_competitor_prices = Mock(return_value={
                "our_price": 10000,
                "competitor_prices": [9500],
                "price_statistics": {
                    "avg": 9500,
                    "min": 9500,
                    "max": 9500
                },
                "position": {"competitiveness": "below_average"}
            })
            MockMonitor.return_value = mock_monitor
            
            # 업로더 Mock
            mock_uploader = Mock()
            mock_uploader.update_price = Mock(return_value={"success": True})
            MockUploader.return_value = mock_uploader
            
            # 작업 실행
            job = PriceAdjustmentJob(storage, {
                "marketplaces": ["coupang"],
                "adjustment_mode": "competitive",
                "min_margin_rate": 10.0
            })
            
            result = await job.run()
            
            # 검증
            assert job.status == JobStatus.COMPLETED
            assert job.stats["total_checked"] >= 1


async def test_order_sync_job():
    """주문 동기화 작업 테스트"""
    storage = MockStorage()
    
    # Mock Order Manager
    with patch('dropshipping.scheduler.jobs.order_sync_job.CoupangOrderManager') as MockManager:
        with patch('dropshipping.scheduler.jobs.order_sync_job.DomemeOrderer') as MockOrderer:
            # 주문 관리자 Mock
            mock_manager = Mock()
            mock_manager.fetch_orders = Mock(return_value=[{
                "marketplace_order_id": "M001",
                "status": "paid",
                "items": [{
                    "product_id": "1",
                    "quantity": 2
                }],
                "customer": {"name": "테스트 고객"},
                "shipping_address": {"address": "테스트 주소"}
            }])
            MockManager.return_value = mock_manager
            
            # 공급사 주문 전달자 Mock
            mock_orderer = Mock()
            mock_orderer.place_batch_order = Mock(return_value={
                "success": True,
                "supplier_order_id": "S001"
            })
            MockOrderer.return_value = mock_orderer
            
            # 테스트 상품 생성
            await storage.create("products", {
                "id": "1",
                "supplier": "domeme",
                "supplier_product_id": "D001"
            })
            
            # 작업 실행
            job = OrderSyncJob(storage, {
                "marketplaces": ["coupang"],
                "sync_mode": "incremental",
                "auto_forward": True
            })
            
            result = await job.run()
            
            # 검증
            assert job.status == JobStatus.COMPLETED
            assert job.stats["total_collected"] >= 1


async def test_report_generation_job():
    """리포트 생성 작업 테스트"""
    storage = MockStorage()
    
    # 테스트 데이터 생성
    # 주문
    await storage.create("orders", {
        "order_date": datetime.now(),
        "status": "delivered",
        "total_amount": 50000,
        "marketplace": "coupang",
        "items": [{
            "product_id": "1",
            "quantity": 2,
            "total_price": 50000
        }]
    })
    
    # 상품
    await storage.create("products", {
        "id": "1",
        "name": "테스트 상품",
        "category_name": "전자제품",
        "base_price": 25000,
        "stock": 10,
        "status": "active"
    })
    
    # 작업 실행
    job = ReportGenerationJob(storage, {
        "report_type": "daily",
        "formats": ["json"],
        "sections": ["sales", "inventory"],
        "send_email": False
    })
    
    result = await job.run()
    
    # 검증
    assert job.status == JobStatus.COMPLETED
    assert job.stats["sections_generated"] == 2
    assert job.stats["formats_created"] >= 1
    
    # 리포트 확인
    reports = await storage.list("reports")
    assert len(reports) == 1
    assert reports[0]["type"] == "daily"
    assert "sales" in reports[0]["sections"]
    assert "inventory" in reports[0]["sections"]


async def test_job_retry():
    """작업 재시도 테스트"""
    storage = MockStorage()
    
    class FailingJob(BaseJob):
        call_count = 0
        
        async def validate(self) -> bool:
            return True
        
        async def execute(self) -> dict:
            FailingJob.call_count += 1
            if FailingJob.call_count < 3:
                raise Exception("의도적인 실패")
            return {"result": "success"}
    
    # 재시도 설정
    job = FailingJob("failing_job", storage, {
        "max_retries": 3,
        "retry_delay": 0.1
    })
    
    # 처음에는 실패
    with pytest.raises(Exception):
        await job.run()
    
    assert job.status == JobStatus.FAILED
    assert job.retry_count == 1


async def test_job_timeout():
    """작업 타임아웃 테스트"""
    storage = MockStorage()
    
    class LongRunningJob(BaseJob):
        async def validate(self) -> bool:
            return True
        
        async def execute(self) -> dict:
            await asyncio.sleep(5)  # 5초 대기
            return {"result": "success"}
    
    # 타임아웃 설정
    job = LongRunningJob("long_job", storage, {
        "timeout": 0.1  # 0.1초 타임아웃
    })
    
    # 타임아웃 발생
    with pytest.raises(asyncio.TimeoutError):
        await job.run()
    
    assert job.status == JobStatus.FAILED
    assert "타임아웃" in job.error


async def test_scheduler_stats():
    """스케줄러 통계 테스트"""
    storage = MockStorage()
    scheduler = BaseScheduler(storage)
    
    # 작업 등록
    scheduler.register_job("test_job", TestJob)
    
    # 작업 실행 시뮬레이션
    await scheduler._execute_job("test_job")
    
    # 통계 확인
    stats = scheduler.get_stats()
    assert stats["total_jobs"] == 1
    assert stats["completed_jobs"] == 1
    assert stats["failed_jobs"] == 0
    assert stats["running_jobs"] == 0


async def test_job_history():
    """작업 이력 조회 테스트"""
    storage = MockStorage()
    scheduler = BaseScheduler(storage)
    
    # 테스트 이력 생성
    await storage.create("job_history", {
        "name": "test_job",
        "status": "completed",
        "updated_at": datetime.now()
    })
    
    await storage.create("job_history", {
        "name": "test_job",
        "status": "failed",
        "updated_at": datetime.now() - timedelta(hours=1)
    })
    
    # 전체 이력 조회
    history = await scheduler.get_job_history()
    assert len(history) == 2
    
    # 상태별 필터링
    completed_history = await scheduler.get_job_history(status=JobStatus.COMPLETED)
    assert len(completed_history) == 1
    assert completed_history[0]["status"] == "completed"


# 실행
async def main():
    """메인 테스트 실행"""
    test_functions = [
        test_base_job,
        test_base_scheduler,
        test_daily_collection_job,
        test_inventory_update_job,
        test_price_adjustment_job,
        test_order_sync_job,
        test_report_generation_job,
        test_job_retry,
        test_job_timeout,
        test_scheduler_stats,
        test_job_history
    ]
    
    for test_func in test_functions:
        print(f"실행 중: {test_func.__name__}")
        try:
            await test_func()
            print(f"✓ {test_func.__name__} 통과")
        except Exception as e:
            print(f"✗ {test_func.__name__} 실패: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())