"""
주문 처리 스케줄러
주기적으로 주문을 처리하는 스케줄러
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from dropshipping.orders.order_processor import OrderProcessor
from dropshipping.storage.base import BaseStorage


class OrderScheduler:
    """주문 처리 스케줄러"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 스케줄러 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # 주문 프로세서
        self.order_processor = OrderProcessor(storage, config)
        
        # 스케줄러
        self.scheduler = AsyncIOScheduler()
        self._setup_jobs()

    def _setup_jobs(self):
        """스케줄 작업 설정"""
        # 신규 주문 수집 (10분마다)
        self.scheduler.add_job(
            self._process_new_orders,
            IntervalTrigger(minutes=self.config.get("new_order_interval", 10)),
            id="process_new_orders",
            name="신규 주문 처리",
            replace_existing=True,
        )

        # 주문 상태 동기화 (30분마다)
        self.scheduler.add_job(
            self._sync_order_status,
            IntervalTrigger(minutes=self.config.get("status_sync_interval", 30)),
            id="sync_order_status",
            name="주문 상태 동기화",
            replace_existing=True,
        )

        # 배송 정보 업데이트 (1시간마다)
        self.scheduler.add_job(
            self._update_tracking_info,
            IntervalTrigger(hours=self.config.get("tracking_update_interval", 1)),
            id="update_tracking_info",
            name="배송 정보 업데이트",
            replace_existing=True,
        )

        # 취소 처리 (30분마다)
        self.scheduler.add_job(
            self._process_cancellations,
            IntervalTrigger(minutes=self.config.get("cancellation_interval", 30)),
            id="process_cancellations",
            name="취소 요청 처리",
            replace_existing=True,
        )

    async def _process_new_orders(self):
        """신규 주문 처리 작업"""
        try:
            logger.info("신규 주문 처리 시작")
            results = await self.order_processor.process_new_orders()
            
            total_orders = sum(results.values())
            logger.info(f"신규 주문 처리 완료: 총 {total_orders}건")
            
            # 처리 결과 저장
            await self._save_job_result("process_new_orders", results)
            
        except Exception as e:
            logger.error(f"신규 주문 처리 실패: {str(e)}")
            await self._save_job_error("process_new_orders", str(e))

    async def _sync_order_status(self):
        """주문 상태 동기화 작업"""
        try:
            logger.info("주문 상태 동기화 시작")
            results = await self.order_processor.sync_order_status()
            
            logger.info(
                f"주문 상태 동기화 완료: "
                f"업데이트 {results['updated']}건, 실패 {results['failed']}건"
            )
            
            await self._save_job_result("sync_order_status", results)
            
        except Exception as e:
            logger.error(f"주문 상태 동기화 실패: {str(e)}")
            await self._save_job_error("sync_order_status", str(e))

    async def _update_tracking_info(self):
        """배송 정보 업데이트 작업"""
        try:
            logger.info("배송 정보 업데이트 시작")
            results = await self.order_processor.update_tracking_info()
            
            logger.info(
                f"배송 정보 업데이트 완료: "
                f"업데이트 {results['updated']}건, 실패 {results['failed']}건"
            )
            
            await self._save_job_result("update_tracking_info", results)
            
        except Exception as e:
            logger.error(f"배송 정보 업데이트 실패: {str(e)}")
            await self._save_job_error("update_tracking_info", str(e))

    async def _process_cancellations(self):
        """취소 처리 작업"""
        try:
            logger.info("취소 요청 처리 시작")
            results = await self.order_processor.process_cancellations()
            
            logger.info(
                f"취소 요청 처리 완료: "
                f"처리 {results['processed']}건, 실패 {results['failed']}건"
            )
            
            await self._save_job_result("process_cancellations", results)
            
        except Exception as e:
            logger.error(f"취소 요청 처리 실패: {str(e)}")
            await self._save_job_error("process_cancellations", str(e))

    async def _save_job_result(self, job_id: str, results: Dict):
        """작업 결과 저장"""
        try:
            await self.storage.save_pipeline_log({
                "job_id": job_id,
                "job_type": "order_processing",
                "status": "success",
                "results": results,
                "executed_at": datetime.now(),
            })
        except Exception as e:
            logger.error(f"작업 결과 저장 실패: {str(e)}")

    async def _save_job_error(self, job_id: str, error: str):
        """작업 오류 저장"""
        try:
            await self.storage.save_pipeline_log({
                "job_id": job_id,
                "job_type": "order_processing",
                "status": "error",
                "error_message": error,
                "executed_at": datetime.now(),
            })
        except Exception as e:
            logger.error(f"작업 오류 저장 실패: {str(e)}")

    def start(self):
        """스케줄러 시작"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("주문 처리 스케줄러 시작됨")
        else:
            logger.warning("주문 처리 스케줄러가 이미 실행 중입니다")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("주문 처리 스케줄러 중지됨")

    def get_jobs(self):
        """현재 스케줄된 작업 목록 반환"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
            })
        return jobs