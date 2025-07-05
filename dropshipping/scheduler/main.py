"""
메인 스케줄러
"""

from typing import Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from dropshipping.config import settings
from dropshipping.monitoring import get_logger, global_metrics
from .jobs import (
    DailyCollectionJob,
    OrderSyncJob,
    PriceAdjustmentJob,
    InventoryUpdateJob,
    ReportGenerationJob
)

logger = get_logger(__name__)


class MainScheduler:
    """메인 스케줄러"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, object] = {}
        self._setup_jobs()
    
    def _setup_jobs(self):
        """작업 설정"""
        # 일일 수집 (매일 오전 2시)
        self.add_job(
            DailyCollectionJob(None),
            CronTrigger(hour=2, minute=0),
            "daily_collection"
        )
        
        # 주문 동기화 (30분마다)
        self.add_job(
            OrderSyncJob(None),
            IntervalTrigger(minutes=30),
            "order_sync"
        )
        
        # 가격 조정 (매일 오전 3시)
        self.add_job(
            PriceAdjustmentJob(None),
            CronTrigger(hour=3, minute=0),
            "price_adjustment"
        )
        
        # 재고 업데이트 (1시간마다)
        self.add_job(
            InventoryUpdateJob(None),
            IntervalTrigger(hours=1),
            "inventory_update"
        )
        
        # 보고서 생성 (매일 오전 7시)
        self.add_job(
            ReportGenerationJob(None),
            CronTrigger(hour=7, minute=0),
            "report_generation"
        )
        
        # 데이터 정리는 나중에 구현
        # self.add_job(
        #     DataCleanupJob(),
        #     CronTrigger(day_of_week=6, hour=4, minute=0),
        #     "data_cleanup"
        # )
        
        logger.info(f"{len(self.jobs)}개의 작업이 설정되었습니다")
    
    def add_job(self, job, trigger, job_id: str):
        """작업 추가"""
        self.jobs[job_id] = job
        
        async def job_wrapper():
            """작업 래퍼"""
            try:
                logger.info(f"작업 시작: {job_id}")
                global_metrics.increment(f"scheduler.{job_id}.started")
                
                result = await job.run()
                
                if result.success:
                    logger.info(f"작업 완료: {job_id}")
                    global_metrics.increment(f"scheduler.{job_id}.success")
                else:
                    logger.error(f"작업 실패: {job_id} - {result.error}")
                    global_metrics.increment(f"scheduler.{job_id}.failed")
                    
            except Exception as e:
                logger.exception(f"작업 오류: {job_id}")
                global_metrics.increment(f"scheduler.{job_id}.error")
        
        self.scheduler.add_job(
            job_wrapper,
            trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1
        )
    
    def start(self):
        """스케줄러 시작"""
        logger.info("스케줄러 시작")
        self.scheduler.start()
    
    def shutdown(self):
        """스케줄러 종료"""
        logger.info("스케줄러 종료")
        self.scheduler.shutdown()
    
    def pause(self):
        """스케줄러 일시정지"""
        self.scheduler.pause()
    
    def resume(self):
        """스케줄러 재개"""
        self.scheduler.resume()
    
    def get_jobs(self) -> List[Dict]:
        """작업 목록 조회"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger)
            })
        return jobs
    
    def run_job(self, job_id: str):
        """작업 즉시 실행"""
        if job_id in self.jobs:
            self.scheduler.add_job(
                self.jobs[job_id].run,
                id=f"{job_id}_manual",
                replace_existing=True
            )
            logger.info(f"작업 수동 실행: {job_id}")
        else:
            logger.error(f"작업을 찾을 수 없음: {job_id}")


def run():
    """스케줄러 실행"""
    import asyncio
    
    scheduler = MainScheduler()
    scheduler.start()
    
    try:
        # 계속 실행
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("스케줄러 중지 요청")
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    run()