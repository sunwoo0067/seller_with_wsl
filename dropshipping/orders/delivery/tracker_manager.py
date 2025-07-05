"""
배송 추적 관리자
여러 택배사의 배송 추적을 통합 관리
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

from loguru import logger

from dropshipping.orders.delivery.base import BaseDeliveryTracker, CarrierType
from dropshipping.orders.delivery.cj_tracker import CJTracker
from dropshipping.orders.delivery.hanjin_tracker import HanjinTracker
from dropshipping.orders.delivery.lotte_tracker import LotteTracker
from dropshipping.orders.delivery.post_tracker import PostTracker
from dropshipping.storage.base import BaseStorage


class TrackerManager:
    """배송 추적 통합 관리자"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 관리자 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # 택배사별 추적기
        self.trackers: Dict[str, BaseDeliveryTracker] = {}
        
        # 기본 설정
        self.batch_size = self.config.get("batch_size", 50)
        self.update_interval = self.config.get("update_interval", 1800)  # 30분
        
        # 통계
        self.stats = {
            "total_tracked": 0,
            "by_carrier": {},
            "errors": []
        }
        
        # 기본 택배사 등록
        self._register_default_trackers()
    
    def _register_default_trackers(self):
        """기본 택배사 추적기 등록"""
        
        # CJ대한통운
        if CarrierType.CJ.value in self.config.get("carriers", ["cj"]):
            self.register_tracker(
                CarrierType.CJ,
                CJTracker(self.storage, self.config.get("cj", {}))
            )
        
        # 한진택배
        if CarrierType.HANJIN.value in self.config.get("carriers", ["hanjin"]):
            self.register_tracker(
                CarrierType.HANJIN,
                HanjinTracker(self.storage, self.config.get("hanjin", {}))
            )
        
        # 롯데글로벌로지스
        if CarrierType.LOTTE.value in self.config.get("carriers", ["lotte"]):
            self.register_tracker(
                CarrierType.LOTTE,
                LotteTracker(self.storage, self.config.get("lotte", {}))
            )
        
        # 우체국택배
        if CarrierType.POST.value in self.config.get("carriers", ["post"]):
            self.register_tracker(
                CarrierType.POST,
                PostTracker(self.storage, self.config.get("post", {}))
            )
    
    def register_tracker(
        self,
        carrier: CarrierType,
        tracker: BaseDeliveryTracker
    ):
        """택배사 추적기 등록"""
        self.trackers[carrier.value] = tracker
        logger.info(f"택배사 추적기 등록: {carrier.value}")
    
    async def track(
        self,
        carrier: str,
        tracking_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        배송 추적
        
        Args:
            carrier: 택배사
            tracking_number: 운송장 번호
            
        Returns:
            배송 정보
        """
        tracker = self.trackers.get(carrier)
        
        if not tracker:
            logger.error(f"등록되지 않은 택배사: {carrier}")
            return None
        
        try:
            result = await tracker.track(tracking_number)
            
            if result:
                self.stats["total_tracked"] += 1
                
                if carrier not in self.stats["by_carrier"]:
                    self.stats["by_carrier"][carrier] = 0
                self.stats["by_carrier"][carrier] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"배송 추적 오류 ({carrier}, {tracking_number}): {str(e)}")
            self.stats["errors"].append({
                "carrier": carrier,
                "tracking_number": tracking_number,
                "error": str(e),
                "timestamp": datetime.now()
            })
            return None
    
    async def track_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        주문 배송 추적
        
        Args:
            order_id: 주문 ID
            
        Returns:
            배송 정보
        """
        try:
            # 주문 조회
            order = await self.storage.get("orders", order_id)
            if not order:
                logger.error(f"주문을 찾을 수 없습니다: {order_id}")
                return None
            
            # 배송 정보 확인
            delivery = order.get("delivery", {})
            carrier = delivery.get("carrier")
            tracking_number = delivery.get("tracking_number")
            
            if not carrier or not tracking_number:
                logger.debug(f"배송 정보가 없습니다: {order_id}")
                return None
            
            # 해당 택배사로 추적
            return await self.track(carrier, tracking_number)
            
        except Exception as e:
            logger.error(f"주문 배송 추적 오류: {str(e)}")
            return None
    
    async def update_all_pending_orders(self) -> Dict[str, Any]:
        """
        모든 배송중 주문 업데이트
        
        Returns:
            업데이트 결과
        """
        logger.info("전체 배송중 주문 업데이트 시작")
        
        results = {
            "total_orders": 0,
            "updated": 0,
            "delivered": 0,
            "failed": 0,
            "by_carrier": {},
            "started_at": datetime.now()
        }
        
        try:
            # 각 택배사별로 업데이트
            tasks = []
            for carrier, tracker in self.trackers.items():
                task = tracker.update_all_pending_orders()
                tasks.append(task)
            
            # 동시 실행
            carrier_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 결과 집계
            for i, (carrier, tracker) in enumerate(self.trackers.items()):
                result = carrier_results[i]
                
                if isinstance(result, Exception):
                    logger.error(f"{carrier} 업데이트 오류: {str(result)}")
                    results["by_carrier"][carrier] = {"error": str(result)}
                else:
                    results["by_carrier"][carrier] = result
                    
                    if "total" in result:
                        results["total_orders"] += result["total"]
                    if "updated" in result:
                        results["updated"] += result["updated"]
                    if "delivered" in result:
                        results["delivered"] += result["delivered"]
                    if "failed" in result:
                        results["failed"] += result["failed"]
            
            results["completed_at"] = datetime.now()
            results["duration"] = (
                results["completed_at"] - results["started_at"]
            ).total_seconds()
            
            logger.info(
                f"배송 업데이트 완료: "
                f"총 {results['total_orders']}개 중 "
                f"{results['updated']}개 업데이트, "
                f"{results['delivered']}개 배송완료"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"전체 배송 업데이트 오류: {str(e)}")
            results["error"] = str(e)
            return results
    
    async def get_tracking_history(
        self,
        carrier: str,
        tracking_number: str
    ) -> List[Dict[str, Any]]:
        """
        배송 이력 조회
        
        Args:
            carrier: 택배사
            tracking_number: 운송장 번호
            
        Returns:
            배송 이력
        """
        tracker = self.trackers.get(carrier)
        
        if not tracker:
            logger.error(f"등록되지 않은 택배사: {carrier}")
            return []
        
        try:
            return await tracker.get_tracking_history(tracking_number)
        except Exception as e:
            logger.error(f"배송 이력 조회 오류: {str(e)}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        stats = {
            **self.stats,
            "trackers": list(self.trackers.keys()),
            "tracker_stats": {}
        }
        
        # 각 택배사별 통계
        for carrier, tracker in self.trackers.items():
            stats["tracker_stats"][carrier] = tracker.get_stats()
        
        return stats
    
    async def close(self):
        """모든 추적기 종료"""
        for tracker in self.trackers.values():
            if hasattr(tracker, "close"):
                await tracker.close()