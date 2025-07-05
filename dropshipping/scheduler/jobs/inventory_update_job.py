"""
재고 업데이트 작업
공급사 재고와 마켓플레이스 재고 동기화
"""

from typing import Dict, Any, List
from datetime import datetime
import asyncio

from loguru import logger

from dropshipping.scheduler.base import BaseJob, JobPriority
from dropshipping.storage.base import BaseStorage
from dropshipping.suppliers.domeme import DomemeFetcher
from dropshipping.suppliers.ownerclan import OwnerclanFetcher
from dropshipping.suppliers.zentrade import ZentradeFetcher
from dropshipping.uploader.coupang import CoupangUploader
from dropshipping.uploader.elevenst import ElevenstUploader
from dropshipping.uploader.smartstore import SmartstoreUploader
from dropshipping.order.inventory_sync import InventorySync


class InventoryUpdateJob(BaseJob):
    """재고 업데이트 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("inventory_update", storage, config)
        
        # 우선순위 높음
        self.priority = JobPriority.HIGH
        
        # 업데이트 설정
        self.suppliers = self.config.get("suppliers", ["domeme", "ownerclan", "zentrade"])
        self.marketplaces = self.config.get("marketplaces", ["coupang", "elevenst", "smartstore"])
        self.batch_size = self.config.get("batch_size", 100)
        self.update_mode = self.config.get("update_mode", "incremental")  # incremental/full
        self.safety_stock_buffer = self.config.get("safety_stock_buffer", 5)
        
        # 공급사/마켓플레이스 초기화
        self.fetchers = self._init_fetchers()
        self.uploaders = self._init_uploaders()
        
        # 재고 동기화 매니저
        self.inventory_sync = InventorySync(storage, config)
        
        # 통계
        self.stats = {
            "total_checked": 0,
            "total_updated": 0,
            "total_failed": 0,
            "supplier_stats": {},
            "marketplace_stats": {}
        }
    
    def _init_fetchers(self) -> Dict[str, Any]:
        """공급사별 Fetcher 초기화"""
        fetchers = {}
        
        if "domeme" in self.suppliers:
            fetchers["domeme"] = DomemeFetcher(
                self.storage,
                self.config.get("domeme", {})
            )
        
        if "ownerclan" in self.suppliers:
            fetchers["ownerclan"] = OwnerclanFetcher(
                self.storage,
                self.config.get("ownerclan", {})
            )
        
        if "zentrade" in self.suppliers:
            fetchers["zentrade"] = ZentradeFetcher(
                self.storage,
                self.config.get("zentrade", {})
            )
        
        return fetchers
    
    def _init_uploaders(self) -> Dict[str, Any]:
        """마켓플레이스별 Uploader 초기화"""
        uploaders = {}
        
        if "coupang" in self.marketplaces:
            uploaders["coupang"] = CoupangUploader(
                self.storage,
                self.config.get("coupang", {})
            )
        
        if "elevenst" in self.marketplaces:
            uploaders["elevenst"] = ElevenstUploader(
                self.storage,
                self.config.get("elevenst", {})
            )
        
        if "smartstore" in self.marketplaces:
            uploaders["smartstore"] = SmartstoreUploader(
                self.storage,
                self.config.get("smartstore", {})
            )
        
        return uploaders
    
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
            logger.warning("재고 업데이트 작업이 이미 실행 중입니다")
            return False
        
        # 공급사/마켓플레이스 설정 확인
        if not self.fetchers or not self.uploaders:
            logger.error("활성화된 공급사 또는 마켓플레이스가 없습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info("재고 업데이트 시작")
        
        if self.update_mode == "incremental":
            # 증분 업데이트: 최근 변경된 상품만
            await self._update_changed_inventory()
        else:
            # 전체 업데이트: 모든 활성 상품
            await self._update_all_inventory()
        
        # 낮은 재고 알림
        await self._check_low_stock_alerts()
        
        # 결과 요약
        self.result = {
            "stats": self.stats,
            "completion_time": datetime.now(),
            "duration": str(datetime.now() - self.start_time)
        }
        
        logger.info(
            f"재고 업데이트 완료: "
            f"확인 {self.stats['total_checked']}개, "
            f"업데이트 {self.stats['total_updated']}개, "
            f"실패 {self.stats['total_failed']}개"
        )
        
        return self.result
    
    async def _update_changed_inventory(self):
        """변경된 재고만 업데이트"""
        logger.info("증분 재고 업데이트 모드")
        
        # 최근 재고 변경 이력 조회
        recent_changes = await self.storage.list(
            "inventory_changes",
            filters={
                "created_at": {
                    "$gte": datetime.now().replace(hour=0, minute=0, second=0),
                    "$lt": datetime.now()
                }
            }
        )
        
        # 변경된 상품 ID 수집
        changed_product_ids = set()
        for change in recent_changes:
            changed_product_ids.add(change["product_id"])
        
        logger.info(f"변경된 상품 수: {len(changed_product_ids)}")
        
        # 배치 처리
        product_ids = list(changed_product_ids)
        for i in range(0, len(product_ids), self.batch_size):
            batch = product_ids[i:i + self.batch_size]
            await self._process_inventory_batch(batch)
    
    async def _update_all_inventory(self):
        """전체 재고 업데이트"""
        logger.info("전체 재고 업데이트 모드")
        
        # 활성 상품 목록 조회
        active_products = await self.storage.list(
            "products",
            filters={"status": "active"}
        )
        
        logger.info(f"활성 상품 수: {len(active_products)}")
        
        # 배치 처리
        for i in range(0, len(active_products), self.batch_size):
            batch = active_products[i:i + self.batch_size]
            batch_ids = [p["id"] for p in batch]
            await self._process_inventory_batch(batch_ids)
    
    async def _process_inventory_batch(self, product_ids: List[str]):
        """재고 배치 처리"""
        for product_id in product_ids:
            try:
                # 상품 정보 조회
                product = await self.storage.get("products", product_id)
                if not product:
                    continue
                
                self.stats["total_checked"] += 1
                
                # 공급사 재고 조회
                supplier_stock = await self._get_supplier_stock(
                    product["supplier"],
                    product["supplier_product_id"]
                )
                
                # 마켓플레이스별 재고 업데이트
                for marketplace_name, uploader in self.uploaders.items():
                    try:
                        # 마켓플레이스 상품 정보 조회
                        listing = await self.storage.get(
                            "listings",
                            filters={
                                "product_id": product_id,
                                "marketplace": marketplace_name,
                                "status": "active"
                            }
                        )
                        
                        if not listing:
                            continue
                        
                        # 재고 업데이트
                        update_result = await uploader.update_stock(
                            listing["marketplace_product_id"],
                            max(0, supplier_stock - self.safety_stock_buffer)
                        )
                        
                        if update_result["success"]:
                            # 업데이트 기록
                            await self.storage.create("inventory_updates", {
                                "product_id": product_id,
                                "marketplace": marketplace_name,
                                "previous_stock": listing.get("stock", 0),
                                "new_stock": supplier_stock - self.safety_stock_buffer,
                                "supplier_stock": supplier_stock,
                                "status": "success",
                                "updated_at": datetime.now()
                            })
                            
                            self.stats["total_updated"] += 1
                            
                            # 마켓플레이스별 통계
                            if marketplace_name not in self.stats["marketplace_stats"]:
                                self.stats["marketplace_stats"][marketplace_name] = {
                                    "updated": 0,
                                    "failed": 0
                                }
                            self.stats["marketplace_stats"][marketplace_name]["updated"] += 1
                        else:
                            raise Exception(update_result.get("error", "Unknown error"))
                    
                    except Exception as e:
                        logger.error(
                            f"재고 업데이트 실패 - "
                            f"상품: {product_id}, "
                            f"마켓플레이스: {marketplace_name}, "
                            f"오류: {str(e)}"
                        )
                        
                        self.stats["total_failed"] += 1
                        if marketplace_name in self.stats["marketplace_stats"]:
                            self.stats["marketplace_stats"][marketplace_name]["failed"] += 1
            
            except Exception as e:
                logger.error(f"상품 재고 처리 실패 - ID: {product_id}, 오류: {str(e)}")
                self.stats["total_failed"] += 1
    
    async def _get_supplier_stock(self, supplier: str, supplier_product_id: str) -> int:
        """공급사 재고 조회"""
        if supplier not in self.fetchers:
            return 0
        
        fetcher = self.fetchers[supplier]
        
        try:
            # 공급사별 재고 조회 메서드 호출
            if hasattr(fetcher, 'get_stock'):
                stock = await fetcher.get_stock(supplier_product_id)
                
                # 공급사별 통계
                if supplier not in self.stats["supplier_stats"]:
                    self.stats["supplier_stats"][supplier] = {
                        "queried": 0,
                        "failed": 0
                    }
                self.stats["supplier_stats"][supplier]["queried"] += 1
                
                return stock
            else:
                # 재고 조회 미지원
                logger.warning(f"{supplier} 공급사는 재고 조회를 지원하지 않습니다")
                return 0
        
        except Exception as e:
            logger.error(f"재고 조회 실패 - 공급사: {supplier}, 상품: {supplier_product_id}, 오류: {str(e)}")
            if supplier in self.stats["supplier_stats"]:
                self.stats["supplier_stats"][supplier]["failed"] += 1
            return 0
    
    async def _check_low_stock_alerts(self):
        """낮은 재고 알림 확인"""
        logger.info("낮은 재고 확인 중...")
        
        # 재고 부족 임계값
        low_stock_threshold = self.config.get("low_stock_threshold", 10)
        
        # 낮은 재고 상품 조회
        low_stock_products = await self.storage.list(
            "inventory_updates",
            filters={
                "new_stock": {"$lte": low_stock_threshold},
                "updated_at": {
                    "$gte": datetime.now().replace(hour=0, minute=0, second=0)
                }
            }
        )
        
        if low_stock_products:
            # 알림 생성
            for item in low_stock_products:
                product = await self.storage.get("products", item["product_id"])
                if product:
                    await self.storage.create("alerts", {
                        "type": "low_stock",
                        "severity": "warning" if item["new_stock"] > 0 else "critical",
                        "product_id": item["product_id"],
                        "product_name": product["name"],
                        "marketplace": item["marketplace"],
                        "current_stock": item["new_stock"],
                        "threshold": low_stock_threshold,
                        "message": f"재고 부족: {product['name']} - 현재 재고 {item['new_stock']}개",
                        "created_at": datetime.now()
                    })
            
            self.stats["low_stock_alerts"] = len(low_stock_products)
            logger.warning(f"낮은 재고 상품 {len(low_stock_products)}개 발견")


class RealTimeInventoryJob(BaseJob):
    """실시간 재고 업데이트 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("realtime_inventory", storage, config)
        
        # 우선순위 높음
        self.priority = JobPriority.CRITICAL
        
        # 설정
        self.check_interval = self.config.get("check_interval", 300)  # 5분
        self.product_ids = self.config.get("product_ids", [])  # 특정 상품만
        
        # 재고 동기화 매니저
        self.inventory_sync = InventorySync(storage, config)
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        if not self.product_ids:
            logger.error("실시간 모니터링할 상품이 지정되지 않았습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info(f"실시간 재고 모니터링 시작 - 상품 {len(self.product_ids)}개")
        
        results = {
            "checked": 0,
            "updated": 0,
            "changes": []
        }
        
        for product_id in self.product_ids:
            try:
                # 재고 동기화
                sync_result = await self.inventory_sync.sync_product_inventory(product_id)
                
                results["checked"] += 1
                
                if sync_result["updated"]:
                    results["updated"] += 1
                    results["changes"].append({
                        "product_id": product_id,
                        "supplier_stock": sync_result["supplier_stock"],
                        "marketplace_updates": sync_result["marketplace_updates"]
                    })
                
            except Exception as e:
                logger.error(f"실시간 재고 확인 실패 - 상품: {product_id}, 오류: {str(e)}")
        
        logger.info(
            f"실시간 재고 모니터링 완료 - "
            f"확인: {results['checked']}, "
            f"업데이트: {results['updated']}"
        )
        
        return results