"""
공급사 관련 API 엔드포인트
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks

from dropshipping.storage.base import BaseStorage
from dropshipping.api.dependencies import (
    get_storage, get_current_user, require_api_key, rate_limiter
)
from dropshipping.suppliers.registry import SupplierRegistry
from dropshipping.monitoring import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/list")
async def list_suppliers(
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """등록된 공급사 목록 조회"""
    try:
        # 레지스트리에서 공급사 목록 가져오기
        registry = SupplierRegistry()
        suppliers = []
        
        for supplier_name in registry.list_suppliers():
            supplier_info = {
                "name": supplier_name,
                "display_name": supplier_name.title(),
                "enabled": True,
                "features": []
            }
            
            # DB에서 추가 정보 조회
            db_supplier = await storage.list(
                "suppliers",
                filters={"name": supplier_name},
                limit=1
            )
            
            if db_supplier:
                supplier_info.update(db_supplier[0])
            
            suppliers.append(supplier_info)
        
        return {"suppliers": suppliers}
        
    except Exception as e:
        logger.error(f"공급사 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="공급사 목록을 조회할 수 없습니다"
        )


@router.get("/{supplier_name}/info")
async def get_supplier_info(
    supplier_name: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """공급사 상세 정보 조회"""
    try:
        # 레지스트리 확인
        registry = SupplierRegistry()
        if supplier_name not in registry.list_suppliers():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="공급사를 찾을 수 없습니다"
            )
        
        # 공급사 인스턴스 생성
        supplier = registry.get_supplier(supplier_name)
        
        # 기본 정보
        info = {
            "name": supplier_name,
            "display_name": supplier_name.title(),
            "type": supplier.__class__.__name__,
            "enabled": True,
            "features": getattr(supplier, "features", []),
            "api_version": getattr(supplier, "api_version", "1.0"),
            "rate_limit": getattr(supplier, "rate_limit", None)
        }
        
        # DB에서 추가 정보 조회
        db_supplier = await storage.list(
            "suppliers",
            filters={"name": supplier_name},
            limit=1
        )
        
        if db_supplier:
            info.update(db_supplier[0])
        
        # 통계 정보
        stats = await storage.get_stats("products")
        info["statistics"] = {
            "total_products": stats.get(supplier_name, {}).get("count", 0),
            "last_sync": stats.get(supplier_name, {}).get("last_sync", None)
        }
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"공급사 정보 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="공급사 정보를 조회할 수 없습니다"
        )


@router.post("/{supplier_name}/sync")
async def sync_supplier_products(
    supplier_name: str,
    background_tasks: BackgroundTasks,
    category: Optional[str] = Query(None, description="특정 카테고리만 동기화"),
    limit: Optional[int] = Query(None, description="동기화할 최대 상품 수"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(require_api_key)
):
    """공급사 상품 동기화"""
    try:
        # 레지스트리 확인
        registry = SupplierRegistry()
        if supplier_name not in registry.list_suppliers():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="공급사를 찾을 수 없습니다"
            )
        
        # 백그라운드 작업으로 동기화 실행
        async def sync_task():
            try:
                supplier = registry.get_supplier(supplier_name)
                # TODO: 실제 동기화 로직 구현
                logger.info(f"{supplier_name} 동기화 시작")
                
                # 동기화 상태 업데이트
                await storage.create("sync_jobs", {
                    "supplier": supplier_name,
                    "status": "completed",
                    "category": category,
                    "limit": limit,
                    "started_at": datetime.utcnow().isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                    "products_synced": 0
                })
                
            except Exception as e:
                logger.error(f"{supplier_name} 동기화 실패: {e}")
                await storage.create("sync_jobs", {
                    "supplier": supplier_name,
                    "status": "failed",
                    "error": str(e),
                    "started_at": datetime.utcnow().isoformat()
                })
        
        background_tasks.add_task(sync_task)
        
        # 작업 ID 생성
        job_id = f"{supplier_name}_{datetime.utcnow().timestamp()}"
        
        return {
            "job_id": job_id,
            "supplier": supplier_name,
            "status": "started",
            "message": "동기화가 백그라운드에서 시작되었습니다"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"공급사 동기화 시작 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="동기화를 시작할 수 없습니다"
        )


@router.get("/{supplier_name}/categories")
async def get_supplier_categories(
    supplier_name: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """공급사 카테고리 목록 조회"""
    try:
        # 레지스트리 확인
        registry = SupplierRegistry()
        if supplier_name not in registry.list_suppliers():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="공급사를 찾을 수 없습니다"
            )
        
        # 공급사별 카테고리 조회
        categories = await storage.query(
            f"""
            SELECT DISTINCT category, COUNT(*) as product_count
            FROM products
            WHERE supplier = '{supplier_name}'
            GROUP BY category
            ORDER BY product_count DESC
            """
        )
        
        return {
            "supplier": supplier_name,
            "categories": [
                {
                    "name": cat["category"],
                    "product_count": cat["product_count"]
                }
                for cat in categories
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"공급사 카테고리 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="카테고리를 조회할 수 없습니다"
        )


@router.put("/{supplier_name}/config")
async def update_supplier_config(
    supplier_name: str,
    config: Dict[str, Any],
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user)
):
    """공급사 설정 업데이트"""
    try:
        # 레지스트리 확인
        registry = SupplierRegistry()
        if supplier_name not in registry.list_suppliers():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="공급사를 찾을 수 없습니다"
            )
        
        # 설정 업데이트
        supplier_data = {
            "name": supplier_name,
            "config": config,
            "updated_by": user["id"],
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # DB 업데이트 또는 생성
        existing = await storage.list(
            "suppliers",
            filters={"name": supplier_name},
            limit=1
        )
        
        if existing:
            updated = await storage.update(
                "suppliers",
                existing[0]["id"],
                supplier_data
            )
        else:
            updated = await storage.create("suppliers", supplier_data)
        
        logger.info(f"공급사 설정 업데이트: {supplier_name}")
        return updated
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"공급사 설정 업데이트 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="설정을 업데이트할 수 없습니다"
        )


@router.get("/sync/jobs")
async def list_sync_jobs(
    supplier: Optional[str] = Query(None, description="공급사 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    limit: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """동기화 작업 목록 조회"""
    try:
        # 필터 조건
        filters = {}
        if supplier:
            filters["supplier"] = supplier
        if status:
            filters["status"] = status
        
        # 작업 목록 조회
        jobs = await storage.list(
            "sync_jobs",
            filters=filters,
            limit=limit,
            order_by=["-started_at"]
        )
        
        return {"jobs": jobs}
        
    except Exception as e:
        logger.error(f"동기화 작업 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="작업 목록을 조회할 수 없습니다"
        )