"""
스케줄러 간단한 테스트
"""

import asyncio
from datetime import datetime

from dropshipping.scheduler.base import BaseJob, BaseScheduler, JobStatus, JobPriority
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
        
        self.data[table][data["id"]] = data
        return data
    
    async def get(self, table: str, id: str = None, filters: dict = None) -> dict:
        if table not in self.data:
            return None
        return self.data[table].get(id) if id else None
    
    async def list(self, table: str, filters: dict = None, limit: int = None) -> list:
        if table not in self.data:
            return []
        items = list(self.data[table].values())
        return items[:limit] if limit else items
    
    async def update(self, table: str, id: str, data: dict) -> dict:
        if table not in self.data or id not in self.data[table]:
            return None
        self.data[table][id].update(data)
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
        return None
    
    async def get_processed_product(self, product_id: str) -> dict:
        return await self.get("products", product_id)
    
    async def list_raw_products(self, supplier: str, limit: int = 100) -> list:
        return []
    
    async def update_status(self, supplier: str, product_id: str, status: str) -> bool:
        return True
    
    async def exists_by_hash(self, data_hash: str) -> bool:
        return False
    
    async def get_stats(self, supplier: str) -> dict:
        return {"total": 0, "processed": 0, "failed": 0}
    
    async def save(self, table: str, data: dict) -> dict:
        return await self.create(table, data)


class TestJob(BaseJob):
    """테스트용 작업"""
    
    async def validate(self) -> bool:
        return True
    
    async def execute(self) -> dict:
        await asyncio.sleep(0.1)
        return {"result": "success"}


async def test_base_job():
    """BaseJob 테스트"""
    print("=== BaseJob 테스트 ===")
    
    storage = MockStorage()
    job = TestJob("test_job", storage)
    
    # 초기 상태
    assert job.name == "test_job"
    assert job.status == JobStatus.PENDING
    assert job.priority == JobPriority.NORMAL
    print("✓ 초기 상태 확인")
    
    # 작업 실행
    result = await job.run()
    
    # 실행 후 상태
    assert job.status == JobStatus.COMPLETED
    assert result == {"result": "success"}
    assert job.start_time is not None
    assert job.end_time is not None
    print("✓ 작업 실행 완료")
    
    # 작업 이력 확인
    history = await storage.list("job_history")
    assert len(history) > 0
    assert history[0]["name"] == "test_job"
    assert history[0]["status"] == "completed"
    print("✓ 작업 이력 저장 확인")


async def test_base_scheduler():
    """BaseScheduler 테스트"""
    print("\n=== BaseScheduler 테스트 ===")
    
    storage = MockStorage()
    scheduler = BaseScheduler(storage)
    
    # 작업 등록
    scheduler.register_job("test_job", TestJob)
    assert "test_job" in scheduler.job_classes
    print("✓ 작업 등록 완료")
    
    # 통계 확인
    stats = scheduler.get_stats()
    assert stats["total_jobs"] == 0
    assert stats["completed_jobs"] == 0
    assert stats["failed_jobs"] == 0
    print("✓ 통계 초기값 확인")


async def test_job_priority():
    """작업 우선순위 테스트"""
    print("\n=== 작업 우선순위 테스트 ===")
    
    storage = MockStorage()
    
    # 다양한 우선순위로 작업 생성
    jobs = []
    for priority in [JobPriority.LOW, JobPriority.NORMAL, JobPriority.HIGH, JobPriority.CRITICAL]:
        job = TestJob(f"job_{priority.value}", storage, {"priority": priority.value})
        assert job.priority == priority
        jobs.append(job)
    
    print("✓ 모든 우선순위 레벨 작업 생성 완료")


async def test_job_configuration():
    """작업 설정 테스트"""
    print("\n=== 작업 설정 테스트 ===")
    
    storage = MockStorage()
    config = {
        "max_retries": 5,
        "retry_delay": 30,
        "timeout": 7200,
        "priority": "high"
    }
    
    job = TestJob("configured_job", storage, config)
    
    assert job.max_retries == 5
    assert job.retry_delay == 30
    assert job.timeout == 7200
    assert job.priority == JobPriority.HIGH
    
    print("✓ 작업 설정 적용 확인")


async def test_failed_job():
    """실패한 작업 테스트"""
    print("\n=== 실패한 작업 테스트 ===")
    
    class FailingJob(BaseJob):
        async def validate(self) -> bool:
            return True
        
        async def execute(self) -> dict:
            raise Exception("의도적인 실패")
    
    storage = MockStorage()
    job = FailingJob("failing_job", storage)
    
    try:
        await job.run()
    except Exception:
        pass
    
    assert job.status == JobStatus.FAILED
    assert job.error == "의도적인 실패"
    assert job.end_time is not None
    
    # 실패 이력 확인
    history = await storage.list("job_history")
    assert len(history) > 0
    assert history[0]["status"] == "failed"
    assert history[0]["error"] == "의도적인 실패"
    
    print("✓ 작업 실패 처리 확인")


async def main():
    """메인 테스트 실행"""
    try:
        await test_base_job()
        await test_base_scheduler()
        await test_job_priority()
        await test_job_configuration()
        await test_failed_job()
        
        print("\n=== 모든 테스트 통과! ===")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())