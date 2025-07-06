"""
스케줄러 시스템 테스트
"""

import asyncio
from datetime import datetime, timedelta
from typing import List

import pytest

from dropshipping.scheduler.base import BaseJob, BaseScheduler, JobPriority, JobResult, JobStatus
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

        id = str(self.id_counter)
        self.id_counter += 1

        self.data[table][id] = {
            "id": id,
            **data,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        return self.data[table][id]

    async def read(self, table: str, id: str) -> dict:
        if table not in self.data or id not in self.data[table]:
            return None
        return self.data[table][id]

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

    async def list(self, table: str, filters: dict = None, limit: int = 100) -> List[dict]:
        if table not in self.data:
            return []

        items = list(self.data[table].values())

        if filters:
            # 간단한 필터링 구현
            filtered = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if key not in item or item[key] != value:
                        match = False
                        break
                if match:
                    filtered.append(item)
            items = filtered

        return items[:limit]

    # 추가 필수 메서드들
    async def save_raw_product(self, product_data: dict) -> dict:
        return await self.create("raw_products", product_data)

    async def save_processed_product(self, product_data: dict) -> dict:
        return await self.create("processed_products", product_data)

    async def get_raw_product(self, product_id: str) -> dict:
        return await self.read("raw_products", product_id)

    async def get_processed_product(self, product_id: str) -> dict:
        return await self.read("processed_products", product_id)

    async def list_raw_products(self, supplier: str = None, limit: int = 100) -> List[dict]:
        filters = {"supplier": supplier} if supplier else None
        return await self.list("raw_products", filters, limit)

    async def update_status(self, table: str, id: str, status: str) -> dict:
        return await self.update(table, id, {"status": status})

    async def exists_by_hash(self, table: str, hash_value: str) -> bool:
        items = await self.list(table, {"hash": hash_value})
        return len(items) > 0

    async def get_stats(self, table: str) -> dict:
        if table not in self.data:
            return {"total": 0}
        return {"total": len(self.data[table])}

    async def save_marketplace_upload(self, upload_data: dict) -> dict:
        return await self.create("marketplace_uploads", upload_data)

    async def get_marketplace_upload(self, upload_id: str) -> dict:
        return await self.read("marketplace_uploads", upload_id)

    async def get_supplier_code(self, supplier_name: str) -> str:
        return f"{supplier_name.upper()}_CODE"

    async def get_marketplace_code(self, marketplace_name: str) -> str:
        return f"{marketplace_name.upper()}_CODE"

    async def get_pricing_rules(self) -> List[dict]:
        return []

    async def get_all_category_mappings(self) -> List[dict]:
        return []

    async def upsert(self, table: str, data: dict, unique_keys: List[str]) -> dict:
        # 간단한 upsert 구현
        items = await self.list(table)
        for item in items:
            match = True
            for key in unique_keys:
                if item.get(key) != data.get(key):
                    match = False
                    break
            if match:
                return await self.update(table, item["id"], data)

        return await self.create(table, data)


class TestJob(BaseJob):
    """테스트용 작업"""

    def __init__(self, job_id: str, name: str, storage: BaseStorage, config: dict = None):
        super().__init__(job_id, name, storage, config)
        self.execute_count = 0
        self.should_fail = config.get("should_fail", False) if config else False
        self.execution_time = config.get("execution_time", 0.1) if config else 0.1

    async def execute(self) -> JobResult:
        """작업 실행"""
        self.execute_count += 1

        # 실행 시간 시뮬레이션
        await asyncio.sleep(self.execution_time)

        if self.should_fail:
            raise Exception("테스트 오류")

        return JobResult(
            job_id=self.job_id,
            status=JobStatus.COMPLETED,
            started_at=datetime.now() - timedelta(seconds=self.execution_time),
            completed_at=datetime.now(),
            result={"count": self.execute_count},
            statistics={"processed": 10, "failed": 0},
        )


class TestScheduler:
    """스케줄러 테스트"""

    @pytest.fixture
    def storage(self):
        return MockStorage()

    @pytest.fixture
    def scheduler(self, storage):
        return BaseScheduler(storage, {"timezone": "Asia/Seoul"})

    def test_job_creation(self, storage):
        """작업 생성 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        assert job.job_id == "test1"
        assert job.name == "테스트 작업"
        assert job.priority == JobPriority.MEDIUM
        assert job.retry_count == 3
        assert job.timeout == 3600

    def test_scheduler_initialization(self, scheduler):
        """스케줄러 초기화 테스트"""
        assert scheduler.is_running == False
        assert len(scheduler.jobs) == 0
        assert len(scheduler.job_history) == 0

    def test_add_job(self, scheduler, storage):
        """작업 추가 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        # 크론 작업 추가
        scheduled_job = scheduler.add_job(job, trigger="cron", hour=10, minute=0)

        assert scheduled_job is not None
        assert scheduled_job.id == "test1"
        assert scheduled_job.name == "테스트 작업"
        assert "test1" in scheduler.jobs

    def test_add_interval_job(self, scheduler, storage):
        """인터벌 작업 추가 테스트"""
        job = TestJob("test2", "인터벌 작업", storage)

        scheduled_job = scheduler.add_job(job, trigger="interval", seconds=30)

        assert scheduled_job is not None
        assert scheduled_job.id == "test2"

    def test_remove_job(self, scheduler, storage):
        """작업 제거 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        scheduler.add_job(job, trigger="interval", seconds=60)
        assert "test1" in scheduler.jobs

        success = scheduler.remove_job("test1")
        assert success == True
        assert "test1" not in scheduler.jobs

    def test_pause_resume_job(self, scheduler, storage):
        """작업 일시정지/재개 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        scheduler.add_job(job, trigger="interval", seconds=60)

        # 일시정지
        success = scheduler.pause_job("test1")
        assert success == True

        # 재개
        success = scheduler.resume_job("test1")
        assert success == True

    def test_get_job_info(self, scheduler, storage):
        """작업 정보 조회 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        scheduler.add_job(job, trigger="cron", hour=10, minute=0)

        info = scheduler.get_job_info("test1")
        assert info is not None
        assert info["id"] == "test1"
        assert info["name"] == "테스트 작업"
        assert "trigger" in info

    def test_get_schedule_summary(self, scheduler, storage):
        """스케줄 요약 조회 테스트"""
        # 여러 작업 추가
        for i in range(3):
            job = TestJob(f"test{i}", f"작업{i}", storage)
            scheduler.add_job(job, trigger="interval", seconds=60 * (i + 1))

        summary = scheduler.get_schedule_summary()
        assert summary["total_jobs"] == 3
        assert summary["is_running"] == False
        assert len(summary["jobs"]) == 3

    @pytest.mark.asyncio
    async def test_job_execution(self, storage):
        """작업 실행 테스트"""
        job = TestJob("test1", "테스트 작업", storage)

        result = await job.run()

        assert result.job_id == "test1"
        assert result.status == JobStatus.COMPLETED
        assert result.result["count"] == 1
        assert result.statistics["processed"] == 10

    @pytest.mark.asyncio
    async def test_job_failure_and_retry(self, storage):
        """작업 실패 및 재시도 테스트"""
        job = TestJob("test1", "실패 작업", storage, {"should_fail": True, "execution_time": 0.01})
        job.retry_count = 2
        job.retry_delay = 0.1

        result = await job.run()

        assert result.status == JobStatus.FAILED
        assert result.error is not None
        assert job.execute_count == 2  # 2번 시도

    @pytest.mark.asyncio
    async def test_job_timeout(self, storage):
        """작업 타임아웃 테스트"""
        job = TestJob("test1", "타임아웃 작업", storage, {"execution_time": 2})
        job.timeout = 0.5  # 0.5초 타임아웃
        job.retry_count = 1

        result = await job.run()

        assert result.status == JobStatus.FAILED
        assert "타임아웃" in result.error

    @pytest.mark.asyncio
    async def test_concurrent_job_prevention(self, storage):
        """동시 실행 방지 테스트"""
        job = TestJob("test1", "동시실행 방지", storage, {"execution_time": 0.5})

        # 두 개의 동시 실행 시도
        task1 = asyncio.create_task(job.run())
        await asyncio.sleep(0.1)  # 첫 번째 작업이 시작되도록 대기
        task2 = asyncio.create_task(job.run())

        result1, result2 = await asyncio.gather(task1, task2)

        # 하나는 성공, 하나는 취소되어야 함
        statuses = {result1.status, result2.status}
        assert JobStatus.COMPLETED in statuses
        assert JobStatus.CANCELLED in statuses

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self, scheduler):
        """스케줄러 시작/종료 테스트"""
        assert scheduler.is_running == False

        # AsyncIOScheduler는 이벤트 루프 내에서 실행되어야 함
        scheduler.start()
        assert scheduler.is_running == True

        # 잠시 대기하여 스케줄러가 완전히 시작되도록 함
        await asyncio.sleep(0.1)

        scheduler.shutdown(wait=False)
        assert scheduler.is_running == False
