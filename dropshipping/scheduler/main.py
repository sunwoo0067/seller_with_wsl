"""
메인 스케줄러
모든 자동화 작업을 관리하는 중앙 스케줄러
"""

import asyncio
from typing import Dict, Any, Optional
import signal
import sys

from loguru import logger

from dropshipping.scheduler.base import BaseScheduler
from dropshipping.scheduler.jobs import (
    DailyCollectionJob,
    IncrementalCollectionJob,
    InventoryUpdateJob,
    RealTimeInventoryJob,
    PriceAdjustmentJob,
    DynamicPricingJob,
    OrderSyncJob,
    OrderStatusCheckJob,
    ReportGenerationJob,
    CustomReportJob
)
from dropshipping.storage.supabase import SupabaseStorage


class MainScheduler:
    """메인 스케줄러"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            config: 스케줄러 설정
        """
        self.config = config or {}
        
        # 스토리지 초기화
        self.storage = SupabaseStorage(self.config.get("storage", {}))
        
        # 기본 스케줄러 초기화
        self.scheduler = BaseScheduler(self.storage, self.config)
        
        # 작업 등록
        self._register_jobs()
        
        # 스케줄 설정
        self._setup_schedules()
        
        # 종료 핸들러
        self._setup_signal_handlers()
    
    def _register_jobs(self):
        """작업 클래스 등록"""
        # 수집 작업
        self.scheduler.register_job("daily_collection", DailyCollectionJob)
        self.scheduler.register_job("incremental_collection", IncrementalCollectionJob)
        
        # 재고 업데이트
        self.scheduler.register_job("inventory_update", InventoryUpdateJob)
        self.scheduler.register_job("realtime_inventory", RealTimeInventoryJob)
        
        # 가격 조정
        self.scheduler.register_job("price_adjustment", PriceAdjustmentJob)
        self.scheduler.register_job("dynamic_pricing", DynamicPricingJob)
        
        # 주문 동기화
        self.scheduler.register_job("order_sync", OrderSyncJob)
        self.scheduler.register_job("order_status_check", OrderStatusCheckJob)
        
        # 리포트 생성
        self.scheduler.register_job("report_generation", ReportGenerationJob)
        self.scheduler.register_job("custom_report", CustomReportJob)
        
        logger.info("모든 작업 클래스 등록 완료")
    
    def _setup_schedules(self):
        """스케줄 설정"""
        schedules = self.config.get("schedules", {})
        
        # 일일 수집 (매일 오전 2시)
        if schedules.get("daily_collection", {}).get("enabled", True):
            self.scheduler.add_cron_job(
                "daily_collection",
                schedules.get("daily_collection", {}).get("cron", "0 2 * * *"),
                config=schedules.get("daily_collection", {}).get("config", {})
            )
        
        # 증분 수집 (매시간)
        if schedules.get("incremental_collection", {}).get("enabled", True):
            self.scheduler.add_interval_job(
                "incremental_collection",
                hours=1,
                config=schedules.get("incremental_collection", {}).get("config", {})
            )
        
        # 재고 업데이트 (30분마다)
        if schedules.get("inventory_update", {}).get("enabled", True):
            self.scheduler.add_interval_job(
                "inventory_update",
                minutes=30,
                config=schedules.get("inventory_update", {}).get("config", {})
            )
        
        # 가격 조정 (매일 오전 6시, 오후 6시)
        if schedules.get("price_adjustment", {}).get("enabled", True):
            self.scheduler.add_cron_job(
                "price_adjustment",
                schedules.get("price_adjustment", {}).get("cron", "0 6,18 * * *"),
                config=schedules.get("price_adjustment", {}).get("config", {})
            )
        
        # 주문 동기화 (5분마다)
        if schedules.get("order_sync", {}).get("enabled", True):
            self.scheduler.add_interval_job(
                "order_sync",
                minutes=5,
                config=schedules.get("order_sync", {}).get("config", {})
            )
        
        # 주문 상태 확인 (1시간마다)
        if schedules.get("order_status_check", {}).get("enabled", True):
            self.scheduler.add_interval_job(
                "order_status_check",
                hours=1,
                config=schedules.get("order_status_check", {}).get("config", {})
            )
        
        # 일일 리포트 (매일 오전 7시)
        if schedules.get("daily_report", {}).get("enabled", True):
            self.scheduler.add_cron_job(
                "report_generation",
                schedules.get("daily_report", {}).get("cron", "0 7 * * *"),
                config={
                    "report_type": "daily",
                    **schedules.get("daily_report", {}).get("config", {})
                }
            )
        
        # 주간 리포트 (매주 월요일 오전 8시)
        if schedules.get("weekly_report", {}).get("enabled", True):
            self.scheduler.add_cron_job(
                "report_generation",
                schedules.get("weekly_report", {}).get("cron", "0 8 * * 1"),
                config={
                    "report_type": "weekly",
                    **schedules.get("weekly_report", {}).get("config", {})
                }
            )
        
        # 월간 리포트 (매월 1일 오전 9시)
        if schedules.get("monthly_report", {}).get("enabled", True):
            self.scheduler.add_cron_job(
                "report_generation",
                schedules.get("monthly_report", {}).get("cron", "0 9 1 * *"),
                config={
                    "report_type": "monthly",
                    **schedules.get("monthly_report", {}).get("config", {})
                }
            )
        
        logger.info("모든 스케줄 설정 완료")
    
    def _setup_signal_handlers(self):
        """시그널 핸들러 설정"""
        def signal_handler(signum, frame):
            logger.info(f"종료 시그널 수신: {signum}")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def start(self):
        """스케줄러 시작"""
        logger.info("=== 드롭쉬핑 자동화 스케줄러 시작 ===")
        
        # 스케줄러 시작
        self.scheduler.start()
        
        # 현재 스케줄 출력
        jobs = self.scheduler.get_jobs()
        logger.info(f"활성 스케줄: {len(jobs)}개")
        for job in jobs:
            logger.info(f"  - {job.name}: {job.trigger}")
        
        logger.info("스케줄러가 실행 중입니다. Ctrl+C로 종료하세요.")
    
    def stop(self):
        """스케줄러 중지"""
        logger.info("스케줄러 종료 중...")
        
        # 실행 중인 작업 대기
        running_jobs = self.scheduler.running_jobs
        if running_jobs:
            logger.info(f"실행 중인 작업 {len(running_jobs)}개 대기 중...")
        
        # 스케줄러 종료
        self.scheduler.stop()
        
        logger.info("스케줄러가 종료되었습니다.")
    
    async def run_forever(self):
        """무한 실행"""
        self.start()
        
        try:
            # 무한 대기
            while True:
                await asyncio.sleep(60)  # 1분마다 체크
                
                # 상태 로깅
                stats = self.scheduler.get_stats()
                logger.debug(
                    f"스케줄러 상태 - "
                    f"총 작업: {stats['total_jobs']}, "
                    f"완료: {stats['completed_jobs']}, "
                    f"실패: {stats['failed_jobs']}, "
                    f"실행 중: {stats['running_jobs']}"
                )
        
        except KeyboardInterrupt:
            logger.info("키보드 인터럽트 감지")
        
        finally:
            self.stop()


def load_config() -> Dict[str, Any]:
    """설정 로드"""
    # TODO: 설정 파일이나 환경 변수에서 로드
    return {
        "storage": {
            "url": "http://localhost:54321",
            "key": "test-key"
        },
        "schedules": {
            "daily_collection": {
                "enabled": True,
                "cron": "0 2 * * *",
                "config": {
                    "suppliers": ["domeme", "ownerclan", "zentrade"],
                    "process_ai": True
                }
            },
            "incremental_collection": {
                "enabled": True,
                "config": {
                    "suppliers": ["domeme"],
                    "lookback_minutes": 60
                }
            },
            "inventory_update": {
                "enabled": True,
                "config": {
                    "update_mode": "incremental",
                    "safety_stock_buffer": 5
                }
            },
            "price_adjustment": {
                "enabled": True,
                "cron": "0 6,18 * * *",
                "config": {
                    "adjustment_mode": "competitive",
                    "min_margin_rate": 10.0
                }
            },
            "order_sync": {
                "enabled": True,
                "config": {
                    "sync_mode": "incremental",
                    "auto_forward": True
                }
            },
            "order_status_check": {
                "enabled": True,
                "config": {
                    "check_pending_hours": 24,
                    "check_shipping_days": 7
                }
            },
            "daily_report": {
                "enabled": True,
                "cron": "0 7 * * *",
                "config": {
                    "send_email": True,
                    "email_recipients": ["admin@example.com"]
                }
            },
            "weekly_report": {
                "enabled": True,
                "cron": "0 8 * * 1"
            },
            "monthly_report": {
                "enabled": True,
                "cron": "0 9 1 * *"
            }
        }
    }


async def main():
    """메인 함수"""
    # 설정 로드
    config = load_config()
    
    # 스케줄러 생성
    scheduler = MainScheduler(config)
    
    # 실행
    await scheduler.run_forever()


if __name__ == "__main__":
    # 로깅 설정
    logger.add(
        "logs/scheduler_{time}.log",
        rotation="1 day",
        retention="30 days",
        level="INFO"
    )
    
    # 실행
    asyncio.run(main())