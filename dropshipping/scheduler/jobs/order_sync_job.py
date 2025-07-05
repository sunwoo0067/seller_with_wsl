"""
주문 동기화 작업
마켓플레이스 주문 수집 및 공급사 주문 전달
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import asyncio

from loguru import logger

from dropshipping.scheduler.base import BaseJob, JobPriority
from dropshipping.storage.base import BaseStorage
from dropshipping.orders.coupang.coupang_order_manager import CoupangOrderManager
from dropshipping.orders.elevenst.elevenst_order_manager import ElevenstOrderManager
from dropshipping.orders.naver.smartstore_order_manager import SmartstoreOrderManager
from dropshipping.orders.supplier.domeme_orderer import DomemeOrderer
from dropshipping.orders.delivery.tracker_manager import TrackerManager


class OrderSyncJob(BaseJob):
    """주문 동기화 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("order_sync", storage, config)
        
        # 우선순위 매우 높음
        self.priority = JobPriority.CRITICAL
        
        # 동기화 설정
        self.marketplaces = self.config.get("marketplaces", ["coupang", "elevenst", "smartstore"])
        self.sync_mode = self.config.get("sync_mode", "incremental")  # incremental/full
        self.lookback_hours = self.config.get("lookback_hours", 1)  # 증분 모드시 조회 기간
        self.auto_forward = self.config.get("auto_forward", True)  # 공급사 자동 주문
        self.batch_size = self.config.get("batch_size", 50)
        
        # 주문 관리자 초기화
        self.order_managers = self._init_order_managers()
        
        # 공급사 주문 전달자
        self.supplier_orderers = self._init_supplier_orderers()
        
        # 배송 추적 관리자
        self.tracker_manager = TrackerManager(storage, config)
        
        # 통계
        self.stats = {
            "total_collected": 0,
            "total_forwarded": 0,
            "total_failed": 0,
            "marketplace_stats": {},
            "supplier_stats": {}
        }
    
    def _init_order_managers(self) -> Dict[str, Any]:
        """마켓플레이스별 주문 관리자 초기화"""
        managers = {}
        
        if "coupang" in self.marketplaces:
            managers["coupang"] = CoupangOrderManager(
                self.storage,
                self.config.get("coupang", {})
            )
        
        if "elevenst" in self.marketplaces:
            managers["elevenst"] = ElevenstOrderManager(
                self.storage,
                self.config.get("elevenst", {})
            )
        
        if "smartstore" in self.marketplaces:
            managers["smartstore"] = SmartstoreOrderManager(
                self.storage,
                self.config.get("smartstore", {})
            )
        
        return managers
    
    def _init_supplier_orderers(self) -> Dict[str, Any]:
        """공급사별 주문 전달자 초기화"""
        orderers = {}
        
        # 현재는 도메매만 지원
        orderers["domeme"] = DomemeOrderer(
            self.storage,
            self.config.get("domeme", {})
        )
        
        return orderers
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        # 이미 실행 중인지 확인
        running_jobs = await self.storage.list(
            "job_history",
            filters={
                "name": self.name,
                "status": "running"
            },
            limit=1
        )
        
        if running_jobs:
            logger.warning("주문 동기화 작업이 이미 실행 중입니다")
            return False
        
        # 마켓플레이스 설정 확인
        if not self.order_managers:
            logger.error("활성화된 마켓플레이스가 없습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info(f"주문 동기화 시작 - 모드: {self.sync_mode}")
        
        # 마켓플레이스별 주문 수집
        all_orders = []
        
        for marketplace_name, manager in self.order_managers.items():
            try:
                orders = await self._collect_marketplace_orders(
                    marketplace_name,
                    manager
                )
                all_orders.extend(orders)
                
            except Exception as e:
                logger.error(f"{marketplace_name} 주문 수집 실패: {str(e)}")
                self.stats["marketplace_stats"][marketplace_name] = {
                    "status": "failed",
                    "error": str(e)
                }
        
        logger.info(f"총 {len(all_orders)}개 주문 수집됨")
        
        # 공급사 주문 전달
        if self.auto_forward and all_orders:
            await self._forward_orders_to_suppliers(all_orders)
        
        # 배송 상태 업데이트
        await self._update_delivery_status()
        
        # 결과 요약
        self.result = {
            "stats": self.stats,
            "completion_time": datetime.now(),
            "duration": str(datetime.now() - self.start_time)
        }
        
        logger.info(
            f"주문 동기화 완료: "
            f"수집 {self.stats['total_collected']}개, "
            f"전달 {self.stats['total_forwarded']}개, "
            f"실패 {self.stats['total_failed']}개"
        )
        
        return self.result
    
    async def _collect_marketplace_orders(
        self,
        marketplace_name: str,
        manager: Any
    ) -> List[Dict[str, Any]]:
        """마켓플레이스 주문 수집"""
        logger.info(f"{marketplace_name} 주문 수집 시작")
        
        marketplace_stats = {
            "collected": 0,
            "new": 0,
            "updated": 0,
            "failed": 0,
            "start_time": datetime.now()
        }
        
        collected_orders = []
        
        try:
            if self.sync_mode == "incremental":
                # 증분 수집: 최근 N시간 주문만
                start_date = datetime.now() - timedelta(hours=self.lookback_hours)
                orders = await manager.fetch_orders(start_date=start_date)
            else:
                # 전체 수집: 미처리 주문 전체
                orders = await manager.fetch_orders(
                    status_filter=["paid", "preparing", "shipping"]
                )
            
            marketplace_stats["collected"] = len(orders)
            self.stats["total_collected"] += len(orders)
            
            # 배치 처리
            for i in range(0, len(orders), self.batch_size):
                batch = orders[i:i + self.batch_size]
                
                for order in batch:
                    try:
                        # 기존 주문 확인
                        existing_order = await self.storage.get(
                            "orders",
                            filters={
                                "marketplace": marketplace_name,
                                "marketplace_order_id": order["marketplace_order_id"]
                            }
                        )
                        
                        if existing_order:
                            # 상태 업데이트
                            if existing_order["status"] != order["status"]:
                                await self.storage.update(
                                    "orders",
                                    existing_order["id"],
                                    {
                                        "status": order["status"],
                                        "updated_at": datetime.now()
                                    }
                                )
                                marketplace_stats["updated"] += 1
                        else:
                            # 새 주문 저장
                            saved_order = await self.storage.create("orders", {
                                **order,
                                "marketplace": marketplace_name,
                                "sync_status": "pending",
                                "created_at": datetime.now()
                            })
                            
                            collected_orders.append(saved_order)
                            marketplace_stats["new"] += 1
                    
                    except Exception as e:
                        logger.error(
                            f"주문 처리 실패 - "
                            f"마켓플레이스: {marketplace_name}, "
                            f"주문번호: {order.get('marketplace_order_id', 'unknown')}, "
                            f"오류: {str(e)}"
                        )
                        marketplace_stats["failed"] += 1
                        self.stats["total_failed"] += 1
                
                # 잠시 대기 (API 제한 회피)
                await asyncio.sleep(0.5)
            
            marketplace_stats["end_time"] = datetime.now()
            marketplace_stats["duration"] = str(
                marketplace_stats["end_time"] - marketplace_stats["start_time"]
            )
            marketplace_stats["status"] = "completed"
        
        except Exception as e:
            marketplace_stats["status"] = "failed"
            marketplace_stats["error"] = str(e)
            raise
        
        finally:
            self.stats["marketplace_stats"][marketplace_name] = marketplace_stats
        
        return collected_orders
    
    async def _forward_orders_to_suppliers(self, orders: List[Dict[str, Any]]):
        """공급사로 주문 전달"""
        logger.info(f"공급사 주문 전달 시작 - {len(orders)}개")
        
        # 공급사별로 주문 그룹화
        supplier_orders = {}
        
        for order in orders:
            # 주문 아이템별로 공급사 확인
            for item in order.get("items", []):
                product = await self.storage.get("products", item["product_id"])
                if not product:
                    continue
                
                supplier = product.get("supplier", "domeme")
                
                if supplier not in supplier_orders:
                    supplier_orders[supplier] = []
                
                supplier_orders[supplier].append({
                    "order": order,
                    "item": item,
                    "product": product
                })
        
        # 공급사별 주문 전달
        for supplier_name, supplier_items in supplier_orders.items():
            if supplier_name not in self.supplier_orderers:
                logger.warning(f"{supplier_name} 공급사 주문 전달 미지원")
                continue
            
            orderer = self.supplier_orderers[supplier_name]
            supplier_stats = {
                "forwarded": 0,
                "failed": 0
            }
            
            # 배치 주문 처리
            batch_orders = []
            
            for item_info in supplier_items:
                try:
                    # 배치에 추가
                    batch_orders.append({
                        "product_id": item_info["product"]["supplier_product_id"],
                        "quantity": item_info["item"]["quantity"],
                        "order_id": item_info["order"]["id"],
                        "customer": item_info["order"]["customer"],
                        "shipping": item_info["order"]["shipping_address"]
                    })
                    
                    # 배치 크기 도달시 전송
                    if len(batch_orders) >= 10:
                        await self._send_batch_orders(
                            orderer,
                            batch_orders,
                            supplier_stats
                        )
                        batch_orders = []
                
                except Exception as e:
                    logger.error(
                        f"주문 준비 실패 - "
                        f"공급사: {supplier_name}, "
                        f"주문: {item_info['order']['id']}, "
                        f"오류: {str(e)}"
                    )
                    supplier_stats["failed"] += 1
                    self.stats["total_failed"] += 1
            
            # 남은 배치 전송
            if batch_orders:
                await self._send_batch_orders(
                    orderer,
                    batch_orders,
                    supplier_stats
                )
            
            self.stats["supplier_stats"][supplier_name] = supplier_stats
            self.stats["total_forwarded"] += supplier_stats["forwarded"]
    
    async def _send_batch_orders(
        self,
        orderer: Any,
        batch_orders: List[Dict[str, Any]],
        stats: Dict[str, int]
    ):
        """배치 주문 전송"""
        try:
            # 공급사로 주문 전송
            result = await orderer.place_batch_order(batch_orders)
            
            if result["success"]:
                stats["forwarded"] += len(batch_orders)
                
                # 주문 상태 업데이트
                for order_info in batch_orders:
                    await self.storage.update(
                        "orders",
                        order_info["order_id"],
                        {
                            "sync_status": "forwarded",
                            "supplier_order_id": result.get("supplier_order_id"),
                            "forwarded_at": datetime.now()
                        }
                    )
                
                logger.info(
                    f"배치 주문 전송 성공 - "
                    f"공급사 주문번호: {result.get('supplier_order_id')}, "
                    f"수량: {len(batch_orders)}"
                )
            else:
                raise Exception(result.get("error", "Unknown error"))
        
        except Exception as e:
            logger.error(f"배치 주문 전송 실패: {str(e)}")
            stats["failed"] += len(batch_orders)
            
            # 주문 상태 업데이트
            for order_info in batch_orders:
                await self.storage.update(
                    "orders",
                    order_info["order_id"],
                    {
                        "sync_status": "failed",
                        "sync_error": str(e),
                        "updated_at": datetime.now()
                    }
                )
    
    async def _update_delivery_status(self):
        """배송 상태 업데이트"""
        logger.info("배송 상태 업데이트 시작")
        
        # 배송 중인 주문 조회
        shipping_orders = await self.storage.list(
            "orders",
            filters={
                "status": {"$in": ["shipping", "in_transit"]},
                "tracking_number": {"$ne": None}
            }
        )
        
        if not shipping_orders:
            return
        
        logger.info(f"배송 추적 대상: {len(shipping_orders)}개")
        
        # 배송 상태 일괄 조회
        tracking_updates = await self.tracker_manager.track_bulk(
            [
                {
                    "carrier": order.get("carrier", "cj"),
                    "tracking_number": order["tracking_number"]
                }
                for order in shipping_orders
            ]
        )
        
        # 상태 업데이트
        updated_count = 0
        
        for order, tracking in zip(shipping_orders, tracking_updates):
            if tracking and tracking.get("status"):
                new_status = self._map_delivery_status(tracking["status"])
                
                if new_status != order["status"]:
                    await self.storage.update(
                        "orders",
                        order["id"],
                        {
                            "status": new_status,
                            "delivery_status": tracking["status"],
                            "delivery_location": tracking.get("current_location"),
                            "delivery_updated_at": tracking.get("updated_at"),
                            "updated_at": datetime.now()
                        }
                    )
                    updated_count += 1
                    
                    # 배송 완료시 마켓플레이스 알림
                    if new_status == "delivered":
                        await self._notify_marketplace_delivery(order)
        
        logger.info(f"배송 상태 업데이트 완료: {updated_count}개")
        self.stats["delivery_updates"] = updated_count
    
    def _map_delivery_status(self, carrier_status: str) -> str:
        """택배사 상태를 시스템 상태로 매핑"""
        status_map = {
            "pickup": "shipping",
            "in_transit": "in_transit",
            "out_for_delivery": "in_transit",
            "delivered": "delivered",
            "failed": "delivery_failed"
        }
        
        return status_map.get(carrier_status, "shipping")
    
    async def _notify_marketplace_delivery(self, order: Dict[str, Any]):
        """마켓플레이스에 배송 완료 통보"""
        marketplace = order["marketplace"]
        
        if marketplace in self.order_managers:
            manager = self.order_managers[marketplace]
            
            try:
                await manager.update_order_status(
                    order["marketplace_order_id"],
                    "delivered"
                )
                
                logger.info(
                    f"배송 완료 통보 - "
                    f"마켓플레이스: {marketplace}, "
                    f"주문번호: {order['marketplace_order_id']}"
                )
            
            except Exception as e:
                logger.error(
                    f"배송 완료 통보 실패 - "
                    f"마켓플레이스: {marketplace}, "
                    f"주문번호: {order['marketplace_order_id']}, "
                    f"오류: {str(e)}"
                )


class OrderStatusCheckJob(BaseJob):
    """주문 상태 확인 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("order_status_check", storage, config)
        
        # 우선순위 보통
        self.priority = JobPriority.NORMAL
        
        # 설정
        self.check_pending_hours = self.config.get("check_pending_hours", 24)
        self.check_shipping_days = self.config.get("check_shipping_days", 7)
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info("주문 상태 확인 시작")
        
        results = {
            "pending_orders": 0,
            "delayed_shipping": 0,
            "cancelled_orders": 0,
            "alerts_created": 0
        }
        
        # 장시간 미처리 주문 확인
        await self._check_pending_orders(results)
        
        # 배송 지연 확인
        await self._check_delayed_shipping(results)
        
        # 취소/반품 처리
        await self._process_cancellations(results)
        
        logger.info(
            f"주문 상태 확인 완료 - "
            f"미처리: {results['pending_orders']}, "
            f"배송지연: {results['delayed_shipping']}, "
            f"취소: {results['cancelled_orders']}"
        )
        
        return results
    
    async def _check_pending_orders(self, results: Dict[str, int]):
        """미처리 주문 확인"""
        threshold = datetime.now() - timedelta(hours=self.check_pending_hours)
        
        pending_orders = await self.storage.list(
            "orders",
            filters={
                "sync_status": "pending",
                "created_at": {"$lte": threshold}
            }
        )
        
        results["pending_orders"] = len(pending_orders)
        
        if pending_orders:
            # 알림 생성
            await self.storage.create("alerts", {
                "type": "pending_orders",
                "severity": "warning",
                "count": len(pending_orders),
                "message": f"{len(pending_orders)}개의 주문이 {self.check_pending_hours}시간 이상 미처리 상태입니다",
                "created_at": datetime.now()
            })
            results["alerts_created"] += 1
    
    async def _check_delayed_shipping(self, results: Dict[str, int]):
        """배송 지연 확인"""
        threshold = datetime.now() - timedelta(days=self.check_shipping_days)
        
        delayed_orders = await self.storage.list(
            "orders",
            filters={
                "status": {"$in": ["shipping", "in_transit"]},
                "forwarded_at": {"$lte": threshold}
            }
        )
        
        results["delayed_shipping"] = len(delayed_orders)
        
        if delayed_orders:
            # 알림 생성
            await self.storage.create("alerts", {
                "type": "delayed_shipping",
                "severity": "high",
                "count": len(delayed_orders),
                "message": f"{len(delayed_orders)}개의 주문이 {self.check_shipping_days}일 이상 배송 중입니다",
                "created_at": datetime.now()
            })
            results["alerts_created"] += 1
    
    async def _process_cancellations(self, results: Dict[str, int]):
        """취소/반품 처리"""
        # TODO: 마켓플레이스별 취소 주문 확인 및 처리
        pass