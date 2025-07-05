"""
재고 동기화 시스템
공급사 재고와 마켓플레이스 재고를 동기화
"""

from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from decimal import Decimal
import asyncio

from loguru import logger

from dropshipping.storage.base import BaseStorage
from dropshipping.suppliers.base.base_fetcher import BaseFetcher
from dropshipping.uploader.base import BaseUploader, MarketplaceType


class InventorySync:
    """재고 동기화 관리자"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: 동기화 설정
        """
        self.storage = storage
        self.config = config or {}
        
        # 동기화 설정
        self.sync_interval = self.config.get("sync_interval", 3600)  # 1시간
        self.batch_size = self.config.get("batch_size", 100)
        self.safety_stock = self.config.get("safety_stock", 5)  # 안전재고
        self.max_stock_diff = self.config.get("max_stock_diff", 10)  # 최대 재고 차이
        
        # 공급사 및 마켓플레이스
        self.suppliers: Dict[str, BaseFetcher] = {}
        self.marketplaces: Dict[str, BaseUploader] = {}
        
        # 통계
        self.stats = {
            "synced": 0,
            "updated": 0,
            "failed": 0,
            "errors": []
        }
    
    def register_supplier(self, name: str, fetcher: BaseFetcher):
        """공급사 등록"""
        self.suppliers[name] = fetcher
        logger.info(f"공급사 등록: {name}")
    
    def register_marketplace(self, name: str, uploader: BaseUploader):
        """마켓플레이스 등록"""
        self.marketplaces[name] = uploader
        logger.info(f"마켓플레이스 등록: {name}")
    
    async def sync_all(self) -> Dict[str, Any]:
        """
        전체 재고 동기화
        
        Returns:
            동기화 결과
        """
        logger.info("전체 재고 동기화 시작")
        start_time = datetime.now()
        
        try:
            # 1. 공급사별 재고 수집
            supplier_stocks = await self._fetch_supplier_stocks()
            
            # 2. 재고 업데이트가 필요한 상품 확인
            products_to_update = await self._find_products_to_update(supplier_stocks)
            
            # 3. 마켓플레이스별 재고 업데이트
            update_results = await self._update_marketplace_stocks(products_to_update)
            
            # 4. 결과 집계
            duration = (datetime.now() - start_time).total_seconds()
            
            result = {
                "synced_at": datetime.now(),
                "duration": duration,
                "total_products": len(supplier_stocks),
                "updated_products": len(products_to_update),
                "marketplace_results": update_results,
                "stats": self.get_stats()
            }
            
            logger.info(
                f"재고 동기화 완료: {len(products_to_update)}개 상품 업데이트 "
                f"(소요시간: {duration:.1f}초)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"재고 동기화 오류: {str(e)}")
            self.stats["failed"] += 1
            self.stats["errors"].append({
                "error": str(e),
                "timestamp": datetime.now()
            })
            raise
    
    async def sync_product(self, product_id: str) -> bool:
        """
        특정 상품 재고 동기화
        
        Args:
            product_id: 상품 ID
            
        Returns:
            성공 여부
        """
        try:
            # 1. 상품 정보 조회
            product = await self.storage.get("products", product_id)
            if not product:
                logger.error(f"상품을 찾을 수 없습니다: {product_id}")
                return False
            
            # 2. 공급사 재고 조회
            supplier = product.get("supplier_id")
            if supplier not in self.suppliers:
                logger.error(f"등록되지 않은 공급사: {supplier}")
                return False
            
            fetcher = self.suppliers[supplier]
            supplier_product = await fetcher.fetch_product(
                product.get("supplier_product_id")
            )
            
            if not supplier_product:
                logger.error(f"공급사 상품을 찾을 수 없습니다: {product_id}")
                return False
            
            # 3. 재고 비교
            current_stock = product.get("stock", 0)
            supplier_stock = supplier_product.get("stock", 0)
            
            # 안전재고 적용
            available_stock = max(0, supplier_stock - self.safety_stock)
            
            if current_stock == available_stock:
                logger.debug(f"재고 변경 없음: {product_id} ({current_stock})")
                return True
            
            # 4. 재고 업데이트
            updates = {
                "stock": available_stock,
                "supplier_stock": supplier_stock,
                "stock_updated_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            await self.storage.update("products", product_id, updates)
            
            # 5. 마켓플레이스 재고 업데이트
            await self._update_marketplace_stock_for_product(
                product_id,
                available_stock
            )
            
            self.stats["updated"] += 1
            logger.info(
                f"재고 업데이트: {product_id} "
                f"({current_stock} -> {available_stock})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"상품 재고 동기화 오류 ({product_id}): {str(e)}")
            self.stats["failed"] += 1
            return False
    
    async def _fetch_supplier_stocks(self) -> Dict[str, Dict[str, Any]]:
        """공급사별 재고 수집"""
        all_stocks = {}
        
        for supplier_name, fetcher in self.suppliers.items():
            try:
                logger.info(f"{supplier_name} 재고 조회 시작")
                
                # 공급사별 재고 조회 (간단 버전)
                # 실제로는 각 공급사의 재고 API 호출
                products = await self._get_supplier_products(supplier_name)
                
                for product in products:
                    product_id = f"{supplier_name}_{product['supplier_product_id']}"
                    all_stocks[product_id] = {
                        "supplier": supplier_name,
                        "supplier_product_id": product["supplier_product_id"],
                        "stock": product.get("stock", 0),
                        "price": product.get("price", 0)
                    }
                
                logger.info(
                    f"{supplier_name} 재고 조회 완료: {len(products)}개 상품"
                )
                
            except Exception as e:
                logger.error(f"{supplier_name} 재고 조회 오류: {str(e)}")
        
        return all_stocks
    
    async def _get_supplier_products(self, supplier_name: str) -> List[Dict[str, Any]]:
        """공급사 상품 목록 조회"""
        # DB에서 해당 공급사 상품 조회
        products = await self.storage.list(
            "products",
            filters={"supplier_id": supplier_name}
        )
        return products
    
    async def _find_products_to_update(
        self,
        supplier_stocks: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """재고 업데이트가 필요한 상품 찾기"""
        products_to_update = []
        
        # 활성 상품 목록 조회
        active_products = await self.storage.list(
            "products",
            filters={"status": "active"}
        )
        
        for product in active_products:
            product_key = f"{product['supplier_id']}_{product['supplier_product_id']}"
            
            if product_key not in supplier_stocks:
                continue
            
            supplier_stock = supplier_stocks[product_key]["stock"]
            current_stock = product.get("stock", 0)
            
            # 안전재고 적용
            available_stock = max(0, supplier_stock - self.safety_stock)
            
            # 재고 차이 확인
            stock_diff = abs(current_stock - available_stock)
            
            # 업데이트 필요 조건
            # 1. 재고 차이가 있음
            # 2. 차이가 최대 허용치 이하
            # 3. 재고가 0이 되거나 0에서 증가하는 경우는 항상 업데이트
            if (stock_diff > 0 and 
                (stock_diff <= self.max_stock_diff or 
                 current_stock == 0 or 
                 available_stock == 0)):
                
                products_to_update.append({
                    "product_id": product["id"],
                    "current_stock": current_stock,
                    "new_stock": available_stock,
                    "supplier_stock": supplier_stock,
                    "marketplace_listings": product.get("marketplace_listings", {})
                })
        
        return products_to_update
    
    async def _update_marketplace_stocks(
        self,
        products_to_update: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, int]]:
        """마켓플레이스별 재고 업데이트"""
        results = {}
        
        for marketplace_name, uploader in self.marketplaces.items():
            results[marketplace_name] = {
                "success": 0,
                "failed": 0
            }
            
            # 해당 마켓플레이스에 등록된 상품만 필터링
            marketplace_products = [
                p for p in products_to_update
                if marketplace_name in p.get("marketplace_listings", {})
            ]
            
            if not marketplace_products:
                continue
            
            logger.info(
                f"{marketplace_name} 재고 업데이트 시작: "
                f"{len(marketplace_products)}개 상품"
            )
            
            # 배치로 나누어 처리
            for i in range(0, len(marketplace_products), self.batch_size):
                batch = marketplace_products[i:i + self.batch_size]
                
                # 동시 업데이트
                tasks = []
                for product_info in batch:
                    task = self._update_single_marketplace_stock(
                        uploader,
                        product_info,
                        marketplace_name
                    )
                    tasks.append(task)
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 결과 집계
                for result in batch_results:
                    if isinstance(result, Exception):
                        results[marketplace_name]["failed"] += 1
                        logger.error(f"재고 업데이트 오류: {str(result)}")
                    elif result:
                        results[marketplace_name]["success"] += 1
                    else:
                        results[marketplace_name]["failed"] += 1
        
        return results
    
    async def _update_single_marketplace_stock(
        self,
        uploader: BaseUploader,
        product_info: Dict[str, Any],
        marketplace_name: str
    ) -> bool:
        """단일 마켓플레이스 재고 업데이트"""
        try:
            listing = product_info["marketplace_listings"].get(marketplace_name, {})
            if not listing:
                return False
            
            marketplace_product_id = listing.get("marketplace_product_id")
            if not marketplace_product_id:
                return False
            
            # 마켓플레이스 재고 업데이트 API 호출
            # 실제로는 각 업로더의 재고 업데이트 메서드 호출
            # 여기서는 간단히 시뮬레이션
            logger.debug(
                f"재고 업데이트: {marketplace_name} - "
                f"{marketplace_product_id} -> {product_info['new_stock']}"
            )
            
            # DB 업데이트
            await self.storage.update(
                "products",
                product_info["product_id"],
                {
                    f"marketplace_listings.{marketplace_name}.stock": product_info["new_stock"],
                    f"marketplace_listings.{marketplace_name}.stock_updated_at": datetime.now()
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"마켓플레이스 재고 업데이트 오류 "
                f"({marketplace_name}, {product_info['product_id']}): {str(e)}"
            )
            return False
    
    async def _update_marketplace_stock_for_product(
        self,
        product_id: str,
        new_stock: int
    ):
        """특정 상품의 모든 마켓플레이스 재고 업데이트"""
        product = await self.storage.get("products", product_id)
        if not product:
            return
        
        marketplace_listings = product.get("marketplace_listings", {})
        
        for marketplace_name, listing in marketplace_listings.items():
            if marketplace_name not in self.marketplaces:
                continue
            
            try:
                uploader = self.marketplaces[marketplace_name]
                marketplace_product_id = listing.get("marketplace_product_id")
                
                if marketplace_product_id:
                    # 실제 마켓플레이스 API 호출
                    logger.debug(
                        f"재고 업데이트: {marketplace_name} - "
                        f"{marketplace_product_id} -> {new_stock}"
                    )
                    
                    # DB 업데이트
                    await self.storage.update(
                        "products",
                        product_id,
                        {
                            f"marketplace_listings.{marketplace_name}.stock": new_stock,
                            f"marketplace_listings.{marketplace_name}.stock_updated_at": datetime.now()
                        }
                    )
                    
            except Exception as e:
                logger.error(
                    f"마켓플레이스 재고 업데이트 오류 "
                    f"({marketplace_name}, {product_id}): {str(e)}"
                )
    
    async def reserve_stock(self, product_id: str, quantity: int) -> bool:
        """
        재고 예약
        
        Args:
            product_id: 상품 ID
            quantity: 예약 수량
            
        Returns:
            성공 여부
        """
        try:
            # 현재 재고 확인
            inventory = await self.storage.get(
                "inventory",
                filters={"product_id": product_id}
            )
            
            if not inventory:
                logger.error(f"재고 정보를 찾을 수 없습니다: {product_id}")
                return False
            
            # 가용 재고 확인
            available = inventory.get("available_stock", 0)
            if available < quantity:
                logger.error(
                    f"재고 부족: {product_id} "
                    f"(요청: {quantity}, 가용: {available})"
                )
                return False
            
            # 재고 예약
            updates = {
                "reserved_stock": inventory.get("reserved_stock", 0) + quantity,
                "available_stock": available - quantity,
                "updated_at": datetime.now()
            }
            
            await self.storage.update("inventory", inventory["id"], updates)
            
            logger.info(
                f"재고 예약 완료: {product_id} - {quantity}개 "
                f"(남은 가용재고: {updates['available_stock']})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"재고 예약 오류: {str(e)}")
            return False
    
    async def confirm_stock(self, product_id: str, quantity: int) -> bool:
        """
        재고 확정 (예약 재고를 실제로 차감)
        
        Args:
            product_id: 상품 ID
            quantity: 확정 수량
            
        Returns:
            성공 여부
        """
        try:
            # 현재 재고 확인
            inventory = await self.storage.get(
                "inventory",
                filters={"product_id": product_id}
            )
            
            if not inventory:
                logger.error(f"재고 정보를 찾을 수 없습니다: {product_id}")
                return False
            
            # 예약 재고 확인
            reserved = inventory.get("reserved_stock", 0)
            if reserved < quantity:
                logger.warning(
                    f"예약 재고 부족: {product_id} "
                    f"(확정 요청: {quantity}, 예약: {reserved})"
                )
                return False
            
            # 재고 차감
            supplier_stock = inventory.get("supplier_stock", 0)
            marketplace_stock = inventory.get("marketplace_stock", 0)
            
            updates = {
                "reserved_stock": reserved - quantity,
                "supplier_stock": supplier_stock - quantity,
                "marketplace_stock": marketplace_stock - quantity,
                "updated_at": datetime.now()
            }
            
            await self.storage.update("inventory", inventory["id"], updates)
            
            logger.info(
                f"재고 확정 완료: {product_id} - {quantity}개 차감 "
                f"(남은 재고: {updates['supplier_stock']})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"재고 확정 오류: {str(e)}")
            return False
    
    async def release_stock(self, product_id: str, quantity: int) -> bool:
        """
        재고 예약 해제
        
        Args:
            product_id: 상품 ID
            quantity: 해제 수량
            
        Returns:
            성공 여부
        """
        try:
            # 현재 재고 확인
            inventory = await self.storage.get(
                "inventory",
                filters={"product_id": product_id}
            )
            
            if not inventory:
                logger.error(f"재고 정보를 찾을 수 없습니다: {product_id}")
                return False
            
            # 예약 재고 확인
            reserved = inventory.get("reserved_stock", 0)
            if reserved < quantity:
                logger.warning(
                    f"예약 재고 부족: {product_id} "
                    f"(해제 요청: {quantity}, 예약: {reserved})"
                )
                quantity = reserved  # 최대한 해제
            
            # 재고 해제
            updates = {
                "reserved_stock": reserved - quantity,
                "available_stock": inventory.get("available_stock", 0) + quantity,
                "updated_at": datetime.now()
            }
            
            await self.storage.update("inventory", inventory["id"], updates)
            
            logger.info(
                f"재고 예약 해제: {product_id} - {quantity}개 "
                f"(가용재고: {updates['available_stock']})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"재고 예약 해제 오류: {str(e)}")
            return False
    
    async def check_low_stock(self, threshold: int = 10) -> List[Dict[str, Any]]:
        """
        낮은 재고 상품 확인
        
        Args:
            threshold: 재고 임계값
            
        Returns:
            낮은 재고 상품 목록
        """
        low_stock_products = await self.storage.list(
            "products",
            filters={
                "status": "active",
                "stock": {"$lte": threshold}
            }
        )
        
        return [
            {
                "product_id": p["id"],
                "name": p["name"],
                "stock": p["stock"],
                "supplier": p["supplier_id"],
                "marketplaces": list(p.get("marketplace_listings", {}).keys())
            }
            for p in low_stock_products
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        total = self.stats["synced"] + self.stats["failed"]
        
        return {
            **self.stats,
            "total": total,
            "success_rate": (
                self.stats["synced"] / total if total > 0 else 0
            )
        }
    
    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "synced": 0,
            "updated": 0,
            "failed": 0,
            "errors": []
        }