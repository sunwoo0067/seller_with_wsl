"""
공급사 주문 전달 기본 클래스
모든 공급사 주문 시스템의 추상 기반 클래스
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import asyncio

from loguru import logger

from dropshipping.models.order import Order, OrderItem, OrderStatus
from dropshipping.storage.base import BaseStorage


class SupplierType(str, Enum):
    """공급사 타입"""
    DOMEME = "domeme"
    DOMEGGOOK = "domeggook"
    OWNERCLAN = "ownerclan"
    ZENTRADE = "zentrade"


class SupplierOrderStatus(str, Enum):
    """공급사 주문 상태"""
    PENDING = "pending"  # 대기중
    ORDERED = "ordered"  # 주문완료
    CONFIRMED = "confirmed"  # 확인됨
    PREPARING = "preparing"  # 준비중
    SHIPPED = "shipped"  # 발송됨
    DELIVERED = "delivered"  # 배송완료
    CANCELLED = "cancelled"  # 취소됨
    FAILED = "failed"  # 실패


class BaseSupplierOrderer(ABC):
    """공급사 주문 전달 기본 클래스"""
    
    def __init__(
        self,
        supplier: SupplierType,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            supplier: 공급사 타입
            storage: 저장소 인스턴스
            config: 공급사 설정
        """
        self.supplier = supplier
        self.storage = storage
        self.config = config or {}
        
        # API 설정
        self.api_key = self.config.get("api_key")
        self.api_secret = self.config.get("api_secret")
        self.seller_id = self.config.get("seller_id")
        
        # 주문 설정
        self.auto_confirm = self.config.get("auto_confirm", True)
        self.batch_size = self.config.get("batch_size", 10)
        self.max_retries = self.config.get("max_retries", 3)
        
        # 통계
        self.stats = {
            "ordered": 0,
            "confirmed": 0,
            "failed": 0,
            "errors": []
        }
    
    @abstractmethod
    async def place_order(
        self,
        order: Order,
        items: List[OrderItem]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        공급사에 주문 전달
        
        Args:
            order: 주문 정보
            items: 주문할 상품 목록
            
        Returns:
            (성공 여부, 결과 데이터)
        """
        pass
    
    @abstractmethod
    async def check_order_status(
        self,
        supplier_order_id: str
    ) -> Dict[str, Any]:
        """
        공급사 주문 상태 확인
        
        Args:
            supplier_order_id: 공급사 주문번호
            
        Returns:
            상태 정보
        """
        pass
    
    @abstractmethod
    async def cancel_order(
        self,
        supplier_order_id: str,
        reason: str
    ) -> bool:
        """
        공급사 주문 취소
        
        Args:
            supplier_order_id: 공급사 주문번호
            reason: 취소 사유
            
        Returns:
            성공 여부
        """
        pass
    
    @abstractmethod
    async def get_tracking_info(
        self,
        supplier_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        배송 정보 조회
        
        Args:
            supplier_order_id: 공급사 주문번호
            
        Returns:
            배송 정보 (carrier, tracking_number 등)
        """
        pass
    
    async def process_order(self, order_id: str) -> bool:
        """
        주문 처리 (전체 프로세스)
        
        Args:
            order_id: 주문 ID
            
        Returns:
            성공 여부
        """
        try:
            # 1. 주문 조회
            order_data = await self.storage.get("orders", order_id)
            if not order_data:
                raise ValueError(f"주문을 찾을 수 없습니다: {order_id}")
            
            order = Order(**order_data)
            
            # 2. 이미 처리된 주문인지 확인
            if order.supplier_order_id:
                logger.info(f"이미 공급사에 전달된 주문: {order_id}")
                return True
            
            # 3. 공급사별 상품 그룹화
            supplier_items = self._group_items_by_supplier(order.items)
            
            # 우리 공급사 상품만 처리
            our_items = supplier_items.get(self.supplier.value, [])
            if not our_items:
                logger.info(f"처리할 {self.supplier.value} 상품이 없습니다")
                return True
            
            # 4. 공급사에 주문 전달
            success, result = await self.place_order(order, our_items)
            
            if success:
                # 5. 주문 정보 업데이트
                supplier_order_id = result.get("order_id")
                updates = {
                    "supplier_order_id": supplier_order_id,
                    "supplier_order_status": SupplierOrderStatus.ORDERED.value,
                    "supplier_ordered_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                
                # 공급사별 주문 정보 저장
                if "supplier_orders" not in order_data:
                    order_data["supplier_orders"] = {}
                
                order_data["supplier_orders"][self.supplier.value] = {
                    "order_id": supplier_order_id,
                    "status": SupplierOrderStatus.ORDERED.value,
                    "ordered_at": datetime.now(),
                    "items": [item.id for item in our_items],
                    "response": result
                }
                
                await self.storage.update("orders", order_id, updates)
                
                self.stats["ordered"] += 1
                logger.info(
                    f"공급사 주문 완료: {order_id} -> {supplier_order_id}"
                )
                
                # 6. 자동 확인 설정시 상태 확인
                if self.auto_confirm:
                    await asyncio.sleep(5)  # 잠시 대기
                    await self.sync_order_status(order_id, supplier_order_id)
                
                return True
            else:
                self.stats["failed"] += 1
                self.stats["errors"].append({
                    "order_id": order_id,
                    "error": result.get("error", "주문 실패"),
                    "timestamp": datetime.now()
                })
                
                logger.error(
                    f"공급사 주문 실패: {order_id} - {result.get('error')}"
                )
                return False
                
        except Exception as e:
            logger.error(f"주문 처리 오류: {str(e)}")
            self.stats["failed"] += 1
            self.stats["errors"].append({
                "order_id": order_id,
                "error": str(e),
                "timestamp": datetime.now()
            })
            return False
    
    async def sync_order_status(
        self,
        order_id: str,
        supplier_order_id: str
    ) -> bool:
        """
        공급사 주문 상태 동기화
        
        Args:
            order_id: 우리 주문 ID
            supplier_order_id: 공급사 주문번호
            
        Returns:
            업데이트 여부
        """
        try:
            # 공급사 상태 조회
            status_info = await self.check_order_status(supplier_order_id)
            
            if not status_info:
                return False
            
            # 상태 업데이트
            updates = {
                "supplier_order_status": status_info.get("status"),
                "updated_at": datetime.now()
            }
            
            # 배송 정보가 있으면 업데이트
            if status_info.get("tracking_number"):
                updates["delivery.tracking_number"] = status_info["tracking_number"]
                updates["delivery.carrier"] = status_info.get("carrier", "")
                updates["delivery.status"] = "in_transit"
            
            await self.storage.update("orders", order_id, updates)
            
            logger.info(
                f"공급사 주문 상태 업데이트: {order_id} - {status_info.get('status')}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"상태 동기화 오류: {str(e)}")
            return False
    
    async def process_batch_orders(
        self,
        order_ids: List[str]
    ) -> Dict[str, bool]:
        """
        배치 주문 처리
        
        Args:
            order_ids: 주문 ID 목록
            
        Returns:
            주문ID별 처리 결과
        """
        results = {}
        
        # 배치 크기로 나누어 처리
        for i in range(0, len(order_ids), self.batch_size):
            batch = order_ids[i:i + self.batch_size]
            
            # 동시 처리
            tasks = [self.process_order(order_id) for order_id in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 결과 저장
            for order_id, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"배치 주문 오류 ({order_id}): {str(result)}")
                    results[order_id] = False
                else:
                    results[order_id] = result
        
        # 통계 로그
        success_count = sum(1 for r in results.values() if r)
        logger.info(
            f"배치 주문 완료: 성공 {success_count}/{len(order_ids)}"
        )
        
        return results
    
    def _group_items_by_supplier(
        self,
        items: List[OrderItem]
    ) -> Dict[str, List[OrderItem]]:
        """상품을 공급사별로 그룹화"""
        grouped = {}
        
        for item in items:
            # supplier_product_id에서 공급사 추출
            # 예: "domeme_12345" -> "domeme"
            supplier = self._extract_supplier(item.supplier_product_id)
            
            if supplier not in grouped:
                grouped[supplier] = []
            grouped[supplier].append(item)
        
        return grouped
    
    def _extract_supplier(self, supplier_product_id: str) -> str:
        """공급사 ID에서 공급사 추출"""
        # 실제로는 더 정교한 로직 필요
        if supplier_product_id.startswith("DM"):
            return SupplierType.DOMEME.value
        elif supplier_product_id.startswith("DG"):
            return SupplierType.DOMEGGOOK.value
        elif supplier_product_id.startswith("OC"):
            return SupplierType.OWNERCLAN.value
        elif supplier_product_id.startswith("ZT"):
            return SupplierType.ZENTRADE.value
        else:
            return "unknown"
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        total = self.stats["ordered"] + self.stats["failed"]
        
        return {
            **self.stats,
            "supplier": self.supplier.value,
            "total": total,
            "success_rate": (
                self.stats["ordered"] / total if total > 0 else 0
            )
        }
    
    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "ordered": 0,
            "confirmed": 0,
            "failed": 0,
            "errors": []
        }
    
    async def _api_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """API 요청 (재시도 포함)"""
        max_retries = self.max_retries
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                # 구체적인 구현은 각 공급사에서
                raise NotImplementedError
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"API 요청 실패 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(retry_delay)