"""
상품 관련 API 엔드포인트
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from dropshipping.storage.base import BaseStorage
from dropshipping.api.dependencies import (
    get_storage, get_current_user, Pagination, 
    require_api_key, rate_limiter
)
from dropshipping.models.product import StandardProduct
from dropshipping.monitoring import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
async def list_products(
    supplier: Optional[str] = Query(None, description="공급사 필터"),
    marketplace: Optional[str] = Query(None, description="마켓플레이스 필터"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    search: Optional[str] = Query(None, description="검색어"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """상품 목록 조회"""
    try:
        # 페이지네이션 설정
        pagination = Pagination(page=page, page_size=page_size)
        
        # 필터 조건 생성
        filters = {}
        if supplier:
            filters["supplier"] = supplier
        if marketplace:
            filters["marketplace"] = marketplace
        if category:
            filters["category"] = category
        if status:
            filters["status"] = status
        
        # 검색 조건
        if search:
            filters["name__icontains"] = search
        
        # 데이터 조회
        products = await storage.list(
            "products",
            filters=filters,
            limit=pagination.limit,
            offset=pagination.offset,
            order_by=["-created_at"]
        )
        
        # 전체 개수 조회
        total = await storage.count("products", filters=filters)
        
        # 응답 생성
        return pagination.paginate(total, products)
        
    except Exception as e:
        logger.error(f"상품 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품 목록을 조회할 수 없습니다"
        )


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """상품 상세 조회"""
    try:
        product = await storage.get("products", product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상품을 찾을 수 없습니다"
            )
        
        return product
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상품 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 조회할 수 없습니다"
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_product(
    product: StandardProduct,
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user)
):
    """상품 생성 (관리자용)"""
    try:
        # 상품 데이터 생성
        product_data = product.model_dump()
        product_data["created_by"] = user["id"]
        product_data["created_at"] = datetime.utcnow().isoformat()
        
        # DB 저장
        created = await storage.create("products", product_data)
        
        logger.info(f"상품 생성됨: {created['id']}")
        return created
        
    except Exception as e:
        logger.error(f"상품 생성 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 생성할 수 없습니다"
        )


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    product: StandardProduct,
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user)
):
    """상품 수정"""
    try:
        # 기존 상품 확인
        existing = await storage.get("products", product_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상품을 찾을 수 없습니다"
            )
        
        # 상품 데이터 업데이트
        product_data = product.model_dump()
        product_data["updated_by"] = user["id"]
        product_data["updated_at"] = datetime.utcnow().isoformat()
        
        # DB 업데이트
        updated = await storage.update("products", product_id, product_data)
        
        logger.info(f"상품 수정됨: {product_id}")
        return updated
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상품 수정 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 수정할 수 없습니다"
        )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user)
):
    """상품 삭제"""
    try:
        # 기존 상품 확인
        existing = await storage.get("products", product_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상품을 찾을 수 없습니다"
            )
        
        # 소프트 삭제
        await storage.update("products", product_id, {
            "status": "deleted",
            "deleted_by": user["id"],
            "deleted_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"상품 삭제됨: {product_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상품 삭제 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 삭제할 수 없습니다"
        )


@router.post("/{product_id}/sync")
async def sync_product(
    product_id: str,
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(require_api_key)
):
    """상품 동기화"""
    try:
        # 기존 상품 확인
        product = await storage.get("products", product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상품을 찾을 수 없습니다"
            )
        
        # TODO: 실제 동기화 로직 구현
        # 1. 공급사 API에서 최신 정보 조회
        # 2. 가격, 재고 등 업데이트
        # 3. 마켓플레이스에 반영
        
        # 임시 응답
        return {
            "product_id": product_id,
            "status": "synced",
            "synced_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상품 동기화 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 동기화할 수 없습니다"
        )


@router.get("/{product_id}/history")
async def get_product_history(
    product_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter)
):
    """상품 변경 이력 조회"""
    try:
        # 페이지네이션 설정
        pagination = Pagination(page=page, page_size=page_size)
        
        # 이력 조회
        history = await storage.list(
            "product_history",
            filters={"product_id": product_id},
            limit=pagination.limit,
            offset=pagination.offset,
            order_by=["-created_at"]
        )
        
        # 전체 개수 조회
        total = await storage.count(
            "product_history",
            filters={"product_id": product_id}
        )
        
        # 응답 생성
        return pagination.paginate(total, history)
        
    except Exception as e:
        logger.error(f"상품 이력 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품 이력을 조회할 수 없습니다"
        )


@router.post("/bulk/update")
async def bulk_update_products(
    product_ids: List[str],
    updates: Dict[str, Any],
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user)
):
    """상품 일괄 수정"""
    try:
        # 업데이트 데이터 준비
        updates["updated_by"] = user["id"]
        updates["updated_at"] = datetime.utcnow().isoformat()
        
        # 일괄 업데이트
        updated_count = 0
        for product_id in product_ids:
            try:
                await storage.update("products", product_id, updates)
                updated_count += 1
            except Exception as e:
                logger.warning(f"상품 {product_id} 업데이트 실패: {e}")
        
        return {
            "requested": len(product_ids),
            "updated": updated_count,
            "failed": len(product_ids) - updated_count
        }
        
    except Exception as e:
        logger.error(f"상품 일괄 수정 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="상품을 일괄 수정할 수 없습니다"
        )