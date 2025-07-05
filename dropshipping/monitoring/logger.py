"""
로깅 시스템
구조화된 로깅과 로그 관리
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


class StructuredFormatter(logging.Formatter):
    """구조화된 JSON 포맷터"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 추가 컨텍스트 정보
        if hasattr(record, "context"):
            log_data["context"] = record.context

        # 예외 정보
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    json_logs: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True,
):
    """
    로깅 시스템 초기화

    Args:
        log_level: 로그 레벨
        log_file: 로그 파일 경로
        json_logs: JSON 형식 로그 사용 여부
        max_bytes: 로그 파일 최대 크기
        backup_count: 백업 파일 개수
        console_output: 콘솔 출력 여부
    """
    # Loguru 설정 초기화
    logger.remove()

    # 로그 레벨 설정
    level = log_level.upper()

    # 콘솔 출력
    if console_output:
        if json_logs:
            logger.add(sys.stdout, level=level, format="{message}", serialize=True)
        else:
            logger.add(
                sys.stdout,
                level=level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                colorize=True,
            )

    # 파일 출력
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        if json_logs:
            # JSON 로그 파일
            logger.add(
                str(log_file),
                level=level,
                format="{message}",
                serialize=True,
                rotation="100 MB",  # 하드코딩된 크기
                retention=backup_count,
                compression="zip",
            )
        else:
            # 일반 로그 파일
            logger.add(
                str(log_file),
                level=level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                rotation="100 MB",  # 하드코딩된 크기
                retention=backup_count,
                compression="zip",
            )

        # 에러 전용 로그 파일
        error_log = log_file.parent / f"{log_file.stem}_error{log_file.suffix}"
        logger.add(
            str(error_log),
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
            rotation="1 day",
            retention="30 days",
            compression="zip",
        )

        # 성능 로그 파일
        perf_log = log_file.parent / f"{log_file.stem}_performance{log_file.suffix}"
        logger.add(
            str(perf_log),
            level="INFO",
            format="{message}",
            filter=lambda record: "performance" in record["extra"],
            serialize=True,
            rotation="1 day",
            retention="7 days",
        )


class LoggerAdapter:
    """컨텍스트 정보를 포함한 로거 어댑터"""

    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self.name = name
        self.context = context or {}
        self._logger = logger.bind(name=name, **self.context)

    def bind(self, **kwargs) -> "LoggerAdapter":
        """새로운 컨텍스트 바인딩"""
        new_context = {**self.context, **kwargs}
        return LoggerAdapter(self.name, new_context)

    def debug(self, message: str, **kwargs):
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        self._logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._logger.critical(message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._logger.exception(message, **kwargs)

    def performance(self, operation: str, duration: float, **kwargs):
        """성능 로그"""
        self._logger.bind(performance=True, operation=operation, duration=duration, **kwargs).info(
            f"Performance: {operation} took {duration:.3f}s"
        )


def get_logger(name: str, **context) -> LoggerAdapter:
    """
    로거 인스턴스 생성

    Args:
        name: 로거 이름
        **context: 컨텍스트 정보

    Returns:
        LoggerAdapter 인스턴스
    """
    return LoggerAdapter(name, context)


# 전역 로거
main_logger = get_logger("dropshipping")
