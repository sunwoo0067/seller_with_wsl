"""
스케줄러 기본 클래스
모든 스케줄 작업의 추상 기반
"""

import asyncio
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from dropshipping.storage.base import BaseStorage


class JobStatus(str, Enum):
    """작업 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class JobPriority(int, Enum):
    """작업 우선순위"""

    LOW = 1
    MEDIUM = 5
    HIGH = 8
    CRITICAL = 10


class JobResult:
    """작업 실행 결과"""

    def __init__(
        self,
        job_id: str,
        status: JobStatus,
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        statistics: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = job_id
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.result = result
        self.error = error
        self.statistics = statistics or {}
        self.duration = (completed_at - started_at).total_seconds() if completed_at else None


class BaseJob(ABC):
    """기본 작업 클래스"""

    def __init__(
        self, job_id: str, name: str, storage: BaseStorage, config: Optional[Dict[str, Any]] = None
    ):
        self.job_id = job_id
        self.name = name
        self.storage = storage
        self.config = config or {}
        self.priority = JobPriority.MEDIUM
        self.retry_count = 3
        self.retry_delay = 60  # seconds
        self.timeout = 3600  # seconds
        self.is_running = False
        self._lock = asyncio.Lock()

    @abstractmethod
    async def execute(self) -> JobResult:
        """작업 실행"""
        pass

    async def run(self) -> JobResult:
        """작업 실행 래퍼"""
        async with self._lock:
            if self.is_running:
                logger.warning(f"작업 {self.name}이(가) 이미 실행 중입니다")
                return JobResult(
                    job_id=self.job_id,
                    status=JobStatus.CANCELLED,
                    started_at=datetime.now(),
                    error="작업이 이미 실행 중",
                )

            self.is_running = True

        started_at = datetime.now()
        attempt = 0
        last_error = None

        try:
            while attempt < self.retry_count:
                try:
                    logger.info(
                        f"작업 {self.name} 실행 시작 " f"(시도 {attempt + 1}/{self.retry_count})"
                    )

                    # 타임아웃 설정
                    result = await asyncio.wait_for(self.execute(), timeout=self.timeout)

                    logger.info(f"작업 {self.name} 실행 완료")
                    return result

                except asyncio.TimeoutError:
                    last_error = f"작업 타임아웃 ({self.timeout}초)"
                    logger.error(f"작업 {self.name} 타임아웃")

                except Exception as e:
                    last_error = str(e)
                    logger.error(f"작업 {self.name} 실행 오류: {e}\n" f"{traceback.format_exc()}")

                attempt += 1
                if attempt < self.retry_count:
                    logger.info(f"작업 {self.name} {self.retry_delay}초 후 재시도...")
                    await asyncio.sleep(self.retry_delay)

            # 모든 재시도 실패
            return JobResult(
                job_id=self.job_id,
                status=JobStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                error=last_error or "알 수 없는 오류",
            )

        finally:
            self.is_running = False

    def validate_config(self) -> bool:
        """설정 검증"""
        return True


class BaseScheduler:
    """기본 스케줄러 클래스"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        self.storage = storage
        self.config = config or {}
        self.scheduler = AsyncIOScheduler(
            timezone=self.config.get("timezone", "Asia/Seoul"),
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
        self.jobs: Dict[str, BaseJob] = {}
        self.job_history: List[JobResult] = []
        self.is_running = False

    def add_job(self, job: BaseJob, trigger: str, **trigger_args) -> Optional[Job]:
        """작업 추가"""
        try:
            if trigger == "cron":
                trigger_obj = CronTrigger(**trigger_args)
            elif trigger == "interval":
                trigger_obj = IntervalTrigger(**trigger_args)
            else:
                logger.error(f"지원하지 않는 트리거 타입: {trigger}")
                return None

            scheduled_job = self.scheduler.add_job(
                func=self._run_job,
                trigger=trigger_obj,
                args=[job],
                id=job.job_id,
                name=job.name,
                replace_existing=True,
            )

            self.jobs[job.job_id] = job
            logger.info(f"작업 {job.name} 스케줄 등록 완료")

            return scheduled_job

        except Exception as e:
            logger.error(f"작업 스케줄 등록 실패: {e}")
            return None

    async def _run_job(self, job: BaseJob):
        """작업 실행 핸들러"""
        try:
            result = await job.run()
            self.job_history.append(result)

            # 실행 이력 저장
            await self._save_job_history(result)

            # 알림 전송
            if result.status == JobStatus.FAILED:
                await self._send_notification(f"작업 실패: {job.name}", f"오류: {result.error}")

        except Exception as e:
            logger.error(f"작업 실행 핸들러 오류: {e}")

    async def _save_job_history(self, result: JobResult):
        """작업 실행 이력 저장"""
        try:
            await self.storage.create(
                "job_history",
                {
                    "job_id": result.job_id,
                    "status": result.status.value,
                    "started_at": result.started_at.isoformat(),
                    "completed_at": (
                        result.completed_at.isoformat() if result.completed_at else None
                    ),
                    "duration": result.duration,
                    "error": result.error,
                    "statistics": result.statistics,
                },
            )
        except Exception as e:
            logger.error(f"작업 이력 저장 실패: {e}")

    async def _send_notification(self, title: str, message: str):
        """알림 전송"""
        # TODO: Slack, 이메일 등 알림 구현
        logger.warning(f"[알림] {title}: {message}")

    def remove_job(self, job_id: str) -> bool:
        """작업 제거"""
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.jobs:
                del self.jobs[job_id]
            logger.info(f"작업 {job_id} 제거 완료")
            return True
        except Exception as e:
            logger.error(f"작업 제거 실패: {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """작업 일시정지"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"작업 {job_id} 일시정지")
            return True
        except Exception as e:
            logger.error(f"작업 일시정지 실패: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """작업 재개"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"작업 {job_id} 재개")
            return True
        except Exception as e:
            logger.error(f"작업 재개 실패: {e}")
            return False

    def start(self):
        """스케줄러 시작"""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("스케줄러 시작됨")

    def shutdown(self, wait: bool = True):
        """스케줄러 종료"""
        if self.is_running:
            self.scheduler.shutdown(wait=wait)
            self.is_running = False
            logger.info("스케줄러 종료됨")

    def get_jobs(self) -> List[Job]:
        """등록된 작업 목록 조회"""
        return self.scheduler.get_jobs()

    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """작업 정보 조회"""
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        # APScheduler 3.x에서는 next_run_time이 직접 접근 가능하지 않음
        # get_next_fire_time() 메서드를 사용해야 함
        next_run = None
        try:
            # 다음 실행 시간 가져오기
            if hasattr(job, "next_run_time") and job.next_run_time:
                next_run = job.next_run_time.isoformat()
            elif hasattr(job.trigger, "get_next_fire_time"):
                next_fire_time = job.trigger.get_next_fire_time(None, datetime.now())
                if next_fire_time:
                    next_run = next_fire_time.isoformat()
        except Exception:
            pass

        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run,
            "trigger": str(job.trigger),
            "pending": getattr(job, "pending", None),
            "coalesce": getattr(job, "coalesce", None),
            "max_instances": getattr(job, "max_instances", 1),
        }

    def get_schedule_summary(self) -> Dict[str, Any]:
        """스케줄 요약 정보"""
        jobs = self.get_jobs()

        # pending 속성이 없는 경우를 처리
        active_jobs = 0
        paused_jobs = 0
        for j in jobs:
            if hasattr(j, "pending") and j.pending:
                paused_jobs += 1
            else:
                active_jobs += 1

        return {
            "is_running": self.is_running,
            "total_jobs": len(jobs),
            "active_jobs": active_jobs,
            "paused_jobs": paused_jobs,
            "jobs": [self.get_job_info(j.id) for j in jobs],
        }
