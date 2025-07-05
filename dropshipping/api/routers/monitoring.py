"""
모니터링 관련 API 엔드포인트
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from dropshipping.api.dependencies import get_storage, rate_limiter, require_api_key
from dropshipping.monitoring import alert_manager, get_logger, global_metrics, performance_tracker
from dropshipping.storage.base import BaseStorage

logger = get_logger(__name__)

router = APIRouter()


@router.get("/metrics")
async def get_metrics(
    category: Optional[str] = Query(None, description="메트릭 카테고리"),
    _: None = Depends(rate_limiter),
):
    """메트릭 조회"""
    try:
        # 전체 메트릭 요약
        summary = global_metrics.get_summary()

        if category:
            # 특정 카테고리만 반환
            if category in summary:
                return summary[category]
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"카테고리를 찾을 수 없습니다: {category}",
                )

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메트릭 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="메트릭을 조회할 수 없습니다"
        )


@router.get("/metrics/export")
async def export_metrics(
    format: str = Query("json", description="내보내기 형식 (json, csv)"),
    _: None = Depends(require_api_key),
):
    """메트릭 내보내기"""
    try:
        metrics = global_metrics.export_metrics()

        if format == "json":
            return StreamingResponse(
                iter([json.dumps(metrics, indent=2)]),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                },
            )
        elif format == "csv":
            # CSV 변환 (간단한 구현)
            csv_lines = ["metric,value,timestamp\n"]
            for category, metrics_dict in metrics.items():
                for metric, value in metrics_dict.items():
                    csv_lines.append(f"{category}.{metric},{value},{datetime.now().isoformat()}\n")

            return StreamingResponse(
                iter(csv_lines),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                },
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="지원하지 않는 형식입니다"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메트릭 내보내기 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="메트릭을 내보낼 수 없습니다"
        )


@router.get("/alerts")
async def get_alerts(
    level: Optional[str] = Query(None, description="알림 레벨 필터"),
    source: Optional[str] = Query(None, description="소스 필터"),
    limit: int = Query(50, ge=1, le=200),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """알림 이력 조회"""
    try:
        # 필터 조건
        filters = {}
        if level:
            filters["level"] = level
        if source:
            filters["source"] = source

        # 알림 이력 조회
        alerts = await storage.list(
            "alerts", filters=filters, limit=limit, order_by=["-created_at"]
        )

        return {"alerts": alerts}

    except Exception as e:
        logger.error(f"알림 이력 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="알림 이력을 조회할 수 없습니다",
        )


@router.post("/alerts/test")
async def send_test_alert(
    channel: str = Query("slack", description="알림 채널 (slack, email, webhook)"),
    _: None = Depends(require_api_key),
):
    """테스트 알림 전송"""
    try:
        # 테스트 알림 전송
        await alert_manager.send(
            title="테스트 알림",
            message="모니터링 시스템 테스트 알림입니다.",
            level="info",
            source="api.test",
            channels=[channel],
        )

        return {"status": "sent", "channel": channel, "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"테스트 알림 전송 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="알림을 전송할 수 없습니다"
        )


@router.get("/performance")
async def get_performance_stats(
    operation: Optional[str] = Query(None, description="작업 이름"), _: None = Depends(rate_limiter)
):
    """성능 통계 조회"""
    try:
        # 성능 통계 가져오기
        stats = performance_tracker.get_stats()

        if operation:
            # 특정 작업의 통계만 반환
            if operation in stats:
                return stats[operation]
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"작업을 찾을 수 없습니다: {operation}",
                )

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"성능 통계 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="성능 통계를 조회할 수 없습니다",
        )


@router.get("/logs")
async def get_logs(
    level: Optional[str] = Query(None, description="로그 레벨 필터"),
    source: Optional[str] = Query(None, description="소스 필터"),
    limit: int = Query(100, ge=1, le=1000),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(require_api_key),
):
    """로그 조회"""
    try:
        # 필터 조건
        filters = {}
        if level:
            filters["level"] = level.upper()
        if source:
            filters["logger__contains"] = source

        # 로그 조회
        logs = await storage.list("logs", filters=filters, limit=limit, order_by=["-timestamp"])

        return {"logs": logs}

    except Exception as e:
        logger.error(f"로그 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="로그를 조회할 수 없습니다"
        )


@router.get("/health/dependencies")
async def check_dependencies(
    storage: BaseStorage = Depends(get_storage), _: None = Depends(rate_limiter)
):
    """의존성 상태 확인"""
    try:
        dependencies = {
            "database": "unknown",
            "redis": "unknown",
            "ollama": "unknown",
            "gemini": "unknown",
        }

        # 데이터베이스 확인
        try:
            await storage.get_stats("products")
            dependencies["database"] = "healthy"
        except:
            dependencies["database"] = "unhealthy"

        # TODO: Redis, Ollama, Gemini 상태 확인 구현

        # 전체 상태 계산
        unhealthy_count = sum(1 for status in dependencies.values() if status != "healthy")
        overall_status = (
            "healthy"
            if unhealthy_count == 0
            else "degraded" if unhealthy_count < len(dependencies) else "unhealthy"
        )

        return {
            "status": overall_status,
            "dependencies": dependencies,
            "checked_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"의존성 상태 확인 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="의존성 상태를 확인할 수 없습니다",
        )


@router.post("/metrics/reset")
async def reset_metrics(
    confirm: bool = Query(False, description="메트릭 초기화 확인"),
    _: None = Depends(require_api_key),
):
    """메트릭 초기화"""
    try:
        if not confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="confirm=true 파라미터가 필요합니다"
            )

        # 메트릭 초기화
        global_metrics.reset()

        logger.warning("메트릭이 초기화되었습니다")

        return {"status": "reset", "timestamp": datetime.utcnow().isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메트릭 초기화 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="메트릭을 초기화할 수 없습니다",
        )


@router.get("/system/info")
async def get_system_info():
    """시스템 정보 조회"""
    try:
        import platform

        import psutil

        # CPU 정보
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # 메모리 정보
        memory = psutil.virtual_memory()

        # 디스크 정보
        disk = psutil.disk_usage("/")

        return {
            "system": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
            },
            "cpu": {"count": cpu_count, "usage_percent": cpu_percent},
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"시스템 정보 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="시스템 정보를 조회할 수 없습니다",
        )
