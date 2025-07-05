"""
스케줄러 기본 클래스
모든 스케줄 작업의 추상 기반
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import traceback

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job

from dropshipping.storage.base import BaseStorage


class JobStatus(str, Enum):
    """작업 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(str, Enum):
    """작업 우선순위"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class BaseJob(ABC):
    """
    기본 작업 클래스
    모든 스케줄 작업이 상속해야 하는 추상 클래스
    """
    
    def __init__(
        self,
        name: str,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            name: 작업 이름
            storage: 저장소 인스턴스
            config: 작업 설정
        """
        self.name = name
        self.storage = storage
        self.config = config or {}
        self.job_id = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 작업 설정
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 60)  # 초
        self.timeout = self.config.get("timeout", 3600)  # 1시간
        self.priority = JobPriority(self.config.get("priority", "normal"))
        
        # 상태
        self.status = JobStatus.PENDING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.retry_count = 0
    
    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """
        작업 실행
        
        Returns:
            실행 결과
        """
        pass
    
    @abstractmethod
    async def validate(self) -> bool:
        """
        작업 실행 전 검증
        
        Returns:
            검증 성공 여부
        """
        pass
    
    async def run(self) -> Dict[str, Any]:
        """
        작업 실행 (검증, 실행, 오류 처리 포함)
        
        Returns:
            실행 결과
        """
        try:
            # 상태 업데이트
            self.status = JobStatus.RUNNING
            self.start_time = datetime.now()
            await self._save_job_status()
            
            # 검증
            if not await self.validate():
                raise ValueError("작업 검증 실패")
            
            # 타임아웃 설정하여 실행
            self.result = await asyncio.wait_for(
                self.execute(),
                timeout=self.timeout
            )
            
            # 성공
            self.status = JobStatus.COMPLETED
            self.end_time = datetime.now()
            await self._save_job_status()
            
            logger.info(
                f"작업 완료: {self.name} "
                f"(소요시간: {self.end_time - self.start_time})"
            )
            
            return self.result
            
        except asyncio.TimeoutError:
            self.error = f"작업 타임아웃 ({self.timeout}초)"
            await self._handle_failure()
            raise
            
        except Exception as e:
            self.error = str(e)
            await self._handle_failure()
            raise
    
    async def _handle_failure(self):
        """작업 실패 처리"""
        self.status = JobStatus.FAILED
        self.end_time = datetime.now()
        
        logger.error(
            f"작업 실패: {self.name}\n"
            f"오류: {self.error}\n"
            f"스택 트레이스:\n{traceback.format_exc()}"
        )
        
        # 재시도 가능 여부 확인
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            logger.info(
                f"작업 재시도 예정: {self.name} "
                f"({self.retry_count}/{self.max_retries})"
            )
            # 재시도는 스케줄러가 처리
        
        await self._save_job_status()
    
    async def _save_job_status(self):
        """작업 상태 저장"""
        await self.storage.save("job_history", {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "priority": self.priority.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
            "result": self.result,
            "retry_count": self.retry_count,
            "updated_at": datetime.now()
        })
    
    def get_duration(self) -> Optional[timedelta]:
        """작업 소요 시간"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "priority": self.priority.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": str(self.get_duration()) if self.get_duration() else None,
            "error": self.error,
            "result": self.result,
            "retry_count": self.retry_count
        }


class BaseScheduler:
    """
    기본 스케줄러 클래스
    APScheduler를 래핑하여 작업 관리
    """
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 스케줄러 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # APScheduler 설정
        scheduler_config = {
            'coalescing': True,  # 지연된 작업 병합
            'max_instances': self.config.get("max_instances", 3),  # 동시 실행 수
            'misfire_grace_time': self.config.get("misfire_grace_time", 60)  # 초
        }
        
        self.scheduler = AsyncIOScheduler(
            job_defaults=scheduler_config,
            timezone=self.config.get("timezone", "Asia/Seoul")
        )
        
        # 작업 레지스트리
        self.job_classes: Dict[str, type[BaseJob]] = {}
        self.running_jobs: Dict[str, BaseJob] = {}
        
        # 통계
        self.stats = {
            "total_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "running_jobs": 0
        }
    
    def register_job(self, name: str, job_class: type[BaseJob]):
        """
        작업 클래스 등록
        
        Args:
            name: 작업 이름
            job_class: 작업 클래스
        """
        self.job_classes[name] = job_class
        logger.info(f"작업 등록: {name}")
    
    def add_cron_job(
        self,
        job_name: str,
        cron_expression: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Job:
        """
        Cron 작업 추가
        
        Args:
            job_name: 작업 이름
            cron_expression: Cron 표현식
            config: 작업 설정
            **kwargs: 추가 스케줄 옵션
            
        Returns:
            스케줄된 작업
        """
        if job_name not in self.job_classes:
            raise ValueError(f"등록되지 않은 작업: {job_name}")
        
        job = self.scheduler.add_job(
            self._execute_job,
            CronTrigger.from_crontab(cron_expression),
            args=[job_name, config],
            id=f"{job_name}_cron",
            name=f"{job_name} (Cron)",
            replace_existing=True,
            **kwargs
        )
        
        logger.info(f"Cron 작업 추가: {job_name} ({cron_expression})")
        return job
    
    def add_interval_job(
        self,
        job_name: str,
        seconds: Optional[int] = None,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Job:
        """
        주기적 작업 추가
        
        Args:
            job_name: 작업 이름
            seconds: 초 간격
            minutes: 분 간격
            hours: 시간 간격
            config: 작업 설정
            **kwargs: 추가 스케줄 옵션
            
        Returns:
            스케줄된 작업
        """
        if job_name not in self.job_classes:
            raise ValueError(f"등록되지 않은 작업: {job_name}")
        
        job = self.scheduler.add_job(
            self._execute_job,
            IntervalTrigger(
                seconds=seconds,
                minutes=minutes,
                hours=hours
            ),
            args=[job_name, config],
            id=f"{job_name}_interval",
            name=f"{job_name} (Interval)",
            replace_existing=True,
            **kwargs
        )
        
        interval_str = []
        if hours:
            interval_str.append(f"{hours}시간")
        if minutes:
            interval_str.append(f"{minutes}분")
        if seconds:
            interval_str.append(f"{seconds}초")
        
        logger.info(
            f"주기적 작업 추가: {job_name} "
            f"(간격: {' '.join(interval_str)})"
        )
        return job
    
    async def _execute_job(
        self,
        job_name: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        작업 실행
        
        Args:
            job_name: 작업 이름
            config: 작업 설정
        """
        job_class = self.job_classes[job_name]
        job = job_class(job_name, self.storage, config)
        
        # 통계 업데이트
        self.stats["total_jobs"] += 1
        self.stats["running_jobs"] += 1
        self.running_jobs[job.job_id] = job
        
        try:
            await job.run()
            self.stats["completed_jobs"] += 1
            
        except Exception as e:
            self.stats["failed_jobs"] += 1
            logger.error(f"작업 실행 실패: {job_name} - {str(e)}")
            
            # 재시도 처리
            if job.retry_count < job.max_retries:
                await asyncio.sleep(job.retry_delay)
                await self._execute_job(job_name, config)
        
        finally:
            self.stats["running_jobs"] -= 1
            if job.job_id in self.running_jobs:
                del self.running_jobs[job.job_id]
    
    def start(self):
        """스케줄러 시작"""
        self.scheduler.start()
        logger.info("스케줄러 시작됨")
    
    def stop(self):
        """스케줄러 중지"""
        self.scheduler.shutdown(wait=True)
        logger.info("스케줄러 중지됨")
    
    def pause(self):
        """스케줄러 일시정지"""
        self.scheduler.pause()
        logger.info("스케줄러 일시정지됨")
    
    def resume(self):
        """스케줄러 재개"""
        self.scheduler.resume()
        logger.info("스케줄러 재개됨")
    
    def get_jobs(self) -> List[Job]:
        """모든 작업 조회"""
        return self.scheduler.get_jobs()
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """특정 작업 조회"""
        return self.scheduler.get_job(job_id)
    
    def remove_job(self, job_id: str):
        """작업 제거"""
        self.scheduler.remove_job(job_id)
        logger.info(f"작업 제거: {job_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        return {
            **self.stats,
            "scheduled_jobs": len(self.get_jobs()),
            "running_job_ids": list(self.running_jobs.keys())
        }
    
    async def get_job_history(
        self,
        limit: int = 100,
        status: Optional[JobStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        작업 실행 이력 조회
        
        Args:
            limit: 조회 개수
            status: 상태 필터
            
        Returns:
            작업 이력 목록
        """
        filters = {}
        if status:
            filters["status"] = status.value
        
        history = await self.storage.list(
            "job_history",
            filters=filters,
            limit=limit
        )
        
        # 최신순 정렬
        history.sort(
            key=lambda x: x.get("updated_at", datetime.min),
            reverse=True
        )
        
        return history