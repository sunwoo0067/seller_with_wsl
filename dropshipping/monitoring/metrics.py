"""
성능 메트릭 시스템
시스템 성능과 비즈니스 메트릭 추적
"""

import asyncio
import statistics
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .logger import get_logger

logger = get_logger(__name__)


class MetricValue:
    """메트릭 값"""

    def __init__(self, value: float, timestamp: Optional[datetime] = None):
        self.value = value
        self.timestamp = timestamp or datetime.now()


class Metric:
    """개별 메트릭"""

    def __init__(self, name: str, metric_type: str = "gauge", window_size: int = 100):
        self.name = name
        self.metric_type = metric_type  # gauge, counter, histogram
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
        self._counter = 0
        self.created_at = datetime.now()

    def record(self, value: float):
        """값 기록"""
        if self.metric_type == "counter":
            self._counter += value
            self.values.append(MetricValue(self._counter))
        else:
            self.values.append(MetricValue(value))

    def increment(self, amount: float = 1):
        """카운터 증가"""
        if self.metric_type == "counter":
            self.record(amount)

    def get_value(self) -> float:
        """현재 값 조회"""
        if not self.values:
            return 0

        if self.metric_type == "counter":
            return self._counter
        else:
            return self.values[-1].value

    def get_stats(self) -> Dict[str, float]:
        """통계 정보"""
        if not self.values:
            return {"count": 0, "mean": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}

        values = [v.value for v in self.values]
        sorted_values = sorted(values)
        count = len(values)

        return {
            "count": count,
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "p50": sorted_values[int(count * 0.5)],
            "p95": sorted_values[int(count * 0.95)] if count > 20 else max(values),
            "p99": sorted_values[int(count * 0.99)] if count > 100 else max(values),
        }


class MetricsCollector:
    """메트릭 수집기"""

    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self._lock = asyncio.Lock()

        # 기본 시스템 메트릭 등록
        self._register_system_metrics()

    def _register_system_metrics(self):
        """시스템 메트릭 등록"""
        # API 메트릭
        self.register("api.requests", "counter")
        self.register("api.errors", "counter")
        self.register("api.latency", "histogram")

        # 데이터베이스 메트릭
        self.register("db.queries", "counter")
        self.register("db.errors", "counter")
        self.register("db.latency", "histogram")

        # 비즈니스 메트릭
        self.register("products.fetched", "counter")
        self.register("products.processed", "counter")
        self.register("products.uploaded", "counter")
        self.register("orders.received", "counter")
        self.register("orders.processed", "counter")

        # AI 메트릭
        self.register("ai.requests", "counter")
        self.register("ai.tokens_used", "counter")
        self.register("ai.cost", "counter")
        self.register("ai.latency", "histogram")

    def register(self, name: str, metric_type: str = "gauge", window_size: int = 100) -> Metric:
        """메트릭 등록"""
        if name not in self.metrics:
            self.metrics[name] = Metric(name, metric_type, window_size)
        return self.metrics[name]

    def record(self, name: str, value: float):
        """값 기록"""
        if name not in self.metrics:
            self.register(name)

        self.metrics[name].record(value)

        # 디버그 로그
        logger.debug(f"Metric recorded: {name}={value}")

    def increment(self, name: str, amount: float = 1):
        """카운터 증가"""
        if name not in self.metrics:
            self.register(name, "counter")

        self.metrics[name].increment(amount)

    def get_metric(self, name: str) -> Optional[Metric]:
        """메트릭 조회"""
        return self.metrics.get(name)

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """모든 메트릭 조회"""
        result = {}

        for name, metric in self.metrics.items():
            result[name] = {
                "type": metric.metric_type,
                "value": metric.get_value(),
                "stats": metric.get_stats() if metric.metric_type == "histogram" else None,
                "created_at": metric.created_at.isoformat(),
            }

        return result

    def get_summary(self) -> Dict[str, Any]:
        """메트릭 요약"""
        total_api_requests = self.metrics.get("api.requests", Metric("", "counter")).get_value()
        total_api_errors = self.metrics.get("api.errors", Metric("", "counter")).get_value()

        return {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "api": {
                    "total_requests": total_api_requests,
                    "total_errors": total_api_errors,
                    "error_rate": total_api_errors / max(total_api_requests, 1),
                    "latency": self.metrics.get("api.latency", Metric("", "histogram")).get_stats(),
                },
                "db": {
                    "total_queries": self.metrics.get(
                        "db.queries", Metric("", "counter")
                    ).get_value(),
                    "total_errors": self.metrics.get(
                        "db.errors", Metric("", "counter")
                    ).get_value(),
                    "latency": self.metrics.get("db.latency", Metric("", "histogram")).get_stats(),
                },
            },
            "business": {
                "products": {
                    "fetched": self.metrics.get(
                        "products.fetched", Metric("", "counter")
                    ).get_value(),
                    "processed": self.metrics.get(
                        "products.processed", Metric("", "counter")
                    ).get_value(),
                    "uploaded": self.metrics.get(
                        "products.uploaded", Metric("", "counter")
                    ).get_value(),
                },
                "orders": {
                    "received": self.metrics.get(
                        "orders.received", Metric("", "counter")
                    ).get_value(),
                    "processed": self.metrics.get(
                        "orders.processed", Metric("", "counter")
                    ).get_value(),
                },
            },
            "ai": {
                "total_requests": self.metrics.get(
                    "ai.requests", Metric("", "counter")
                ).get_value(),
                "total_tokens": self.metrics.get(
                    "ai.tokens_used", Metric("", "counter")
                ).get_value(),
                "total_cost": self.metrics.get("ai.cost", Metric("", "counter")).get_value(),
                "latency": self.metrics.get("ai.latency", Metric("", "histogram")).get_stats(),
            },
        }


class PerformanceTracker:
    """성능 추적기"""

    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics = metrics_collector or MetricsCollector()

    @contextmanager
    def track(self, operation: str, metric_name: Optional[str] = None):
        """동기 작업 성능 추적"""
        start_time = time.time()
        error_occurred = False

        try:
            yield
        except Exception as e:
            error_occurred = True
            logger.error(f"Error in {operation}: {str(e)}")
            raise
        finally:
            duration = time.time() - start_time

            # 메트릭 기록
            if metric_name:
                self.metrics.record(metric_name, duration)

            # 로그
            logger.performance(operation, duration, error=error_occurred)

    @asynccontextmanager
    async def track_async(self, operation: str, metric_name: Optional[str] = None):
        """비동기 작업 성능 추적"""
        start_time = time.time()
        error_occurred = False

        try:
            yield
        except Exception as e:
            error_occurred = True
            logger.error(f"Error in {operation}: {str(e)}")
            raise
        finally:
            duration = time.time() - start_time

            # 메트릭 기록
            if metric_name:
                self.metrics.record(metric_name, duration)

            # 로그
            logger.performance(operation, duration, error=error_occurred)

    def measure(self, metric_name: Optional[str] = None):
        """데코레이터로 사용"""

        def decorator(func: Callable):
            if asyncio.iscoroutinefunction(func):

                async def async_wrapper(*args, **kwargs):
                    async with self.track_async(func.__name__, metric_name):
                        return await func(*args, **kwargs)

                return async_wrapper
            else:

                def sync_wrapper(*args, **kwargs):
                    with self.track(func.__name__, metric_name):
                        return func(*args, **kwargs)

                return sync_wrapper

        return decorator


# 전역 메트릭 수집기
global_metrics = MetricsCollector()
performance_tracker = PerformanceTracker(global_metrics)
