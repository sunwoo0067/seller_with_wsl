"""
일일 수집 작업
공급사별 상품 데이터 수집 및 처리
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import asyncio

from loguru import logger

from dropshipping.scheduler.base import BaseJob, JobPriority
from dropshipping.storage.base import BaseStorage
from dropshipping.suppliers.domeme import DomemeFetcher
from dropshipping.suppliers.ownerclan import OwnerclanFetcher
from dropshipping.suppliers.zentrade import ZentradeFetcher
from dropshipping.transformers.domeme import DomemeTransformer
from dropshipping.suppliers.ownerclan.transformer import OwnerclanTransformer
from dropshipping.suppliers.zentrade.transformer import ZentradeTransformer
from dropshipping.ai_processors.pipeline import AIProcessingPipeline


class DailyCollectionJob(BaseJob):
    """일일 상품 수집 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("daily_collection", storage, config)
        
        # 우선순위 높음
        self.priority = JobPriority.HIGH
        
        # 수집 설정
        self.suppliers = self.config.get("suppliers", ["domeme", "ownerclan", "zentrade"])
        self.batch_size = self.config.get("batch_size", 50)
        self.process_ai = self.config.get("process_ai", True)
        self.max_products_per_supplier = self.config.get("max_products_per_supplier", 1000)
        
        # 공급사별 Fetcher 초기화
        self.fetchers = self._init_fetchers()
        self.transformers = self._init_transformers()
        
        # AI 처리 파이프라인
        if self.process_ai:
            self.ai_pipeline = AIProcessingPipeline(storage, config)
        
        # 통계
        self.stats = {
            "total_fetched": 0,
            "total_processed": 0,
            "total_failed": 0,
            "supplier_stats": {}
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
    
    def _init_transformers(self) -> Dict[str, Any]:
        """공급사별 Transformer 초기화"""
        transformers = {}
        
        if "domeme" in self.suppliers:
            transformers["domeme"] = DomemeTransformer()
        
        if "ownerclan" in self.suppliers:
            transformers["ownerclan"] = OwnerclanTransformer()
        
        if "zentrade" in self.suppliers:
            transformers["zentrade"] = ZentradeTransformer()
        
        return transformers
    
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
            logger.warning("일일 수집 작업이 이미 실행 중입니다")
            return False
        
        # 공급사 설정 확인
        if not self.fetchers:
            logger.error("활성화된 공급사가 없습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info("일일 상품 수집 시작")
        
        # 각 공급사별로 수집
        for supplier_name, fetcher in self.fetchers.items():
            try:
                await self._collect_from_supplier(
                    supplier_name,
                    fetcher,
                    self.transformers[supplier_name]
                )
            except Exception as e:
                logger.error(f"{supplier_name} 수집 실패: {str(e)}")
                self.stats["supplier_stats"][supplier_name] = {
                    "status": "failed",
                    "error": str(e)
                }
        
        # AI 처리
        if self.process_ai and self.stats["total_processed"] > 0:
            await self._process_with_ai()
        
        # 결과 요약
        self.result = {
            "stats": self.stats,
            "completion_time": datetime.now(),
            "duration": str(datetime.now() - self.start_time)
        }
        
        logger.info(
            f"일일 수집 완료: "
            f"수집 {self.stats['total_fetched']}개, "
            f"처리 {self.stats['total_processed']}개, "
            f"실패 {self.stats['total_failed']}개"
        )
        
        return self.result
    
    async def _collect_from_supplier(
        self,
        supplier_name: str,
        fetcher: Any,
        transformer: Any
    ):
        """공급사별 수집"""
        logger.info(f"{supplier_name} 수집 시작")
        
        supplier_stats = {
            "fetched": 0,
            "processed": 0,
            "failed": 0,
            "start_time": datetime.now()
        }
        
        try:
            # 최신 상품부터 수집
            products = await fetcher.fetch_products(
                limit=self.max_products_per_supplier,
                sort_by="newest"
            )
            
            supplier_stats["fetched"] = len(products)
            self.stats["total_fetched"] += len(products)
            
            # 배치 처리
            for i in range(0, len(products), self.batch_size):
                batch = products[i:i + self.batch_size]
                
                for product in batch:
                    try:
                        # 이미 처리된 상품인지 확인
                        if await fetcher.is_processed(product):
                            continue
                        
                        # 표준 형식으로 변환
                        standard_product = transformer.transform(product)
                        
                        # 저장
                        await self.storage.save_processed_product(
                            standard_product.dict()
                        )
                        
                        # 상태 업데이트
                        await fetcher.mark_as_processed(product)
                        
                        supplier_stats["processed"] += 1
                        self.stats["total_processed"] += 1
                        
                    except Exception as e:
                        logger.error(
                            f"{supplier_name} 상품 처리 실패: {str(e)}"
                        )
                        supplier_stats["failed"] += 1
                        self.stats["total_failed"] += 1
                
                # 잠시 대기 (API 제한 회피)
                await asyncio.sleep(1)
            
            supplier_stats["end_time"] = datetime.now()
            supplier_stats["duration"] = str(
                supplier_stats["end_time"] - supplier_stats["start_time"]
            )
            supplier_stats["status"] = "completed"
            
        except Exception as e:
            supplier_stats["status"] = "failed"
            supplier_stats["error"] = str(e)
            raise
        
        finally:
            self.stats["supplier_stats"][supplier_name] = supplier_stats
    
    async def _process_with_ai(self):
        """AI 처리"""
        logger.info("AI 처리 시작")
        
        try:
            # 오늘 수집된 상품 조회
            today = datetime.now().date()
            products = await self.storage.list(
                "products",
                filters={
                    "created_at": {
                        "$gte": datetime.combine(today, datetime.min.time()),
                        "$lt": datetime.combine(today + timedelta(days=1), datetime.min.time())
                    },
                    "ai_processed": {"$ne": True}
                },
                limit=100  # AI 처리 제한
            )
            
            if products:
                # AI 파이프라인 실행
                results = await self.ai_pipeline.process_batch(products)
                
                # 결과 저장
                for product_id, result in results.items():
                    if result["success"]:
                        await self.storage.update(
                            "products",
                            product_id,
                            {
                                **result["enhancements"],
                                "ai_processed": True,
                                "ai_processed_at": datetime.now()
                            }
                        )
                
                self.stats["ai_processed"] = len([r for r in results.values() if r["success"]])
                logger.info(f"AI 처리 완료: {self.stats['ai_processed']}개")
            
        except Exception as e:
            logger.error(f"AI 처리 실패: {str(e)}")
            self.stats["ai_error"] = str(e)


class IncrementalCollectionJob(BaseJob):
    """증분 수집 작업 (시간별)"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("incremental_collection", storage, config)
        
        # 우선순위 보통
        self.priority = JobPriority.NORMAL
        
        # 수집 설정
        self.suppliers = self.config.get("suppliers", ["domeme"])  # 빠른 API만
        self.lookback_minutes = self.config.get("lookback_minutes", 60)
        self.batch_size = self.config.get("batch_size", 20)
        
        # 공급사별 Fetcher 초기화
        self.fetchers = self._init_fetchers()
        self.transformers = self._init_transformers()
    
    def _init_fetchers(self) -> Dict[str, Any]:
        """공급사별 Fetcher 초기화"""
        fetchers = {}
        
        if "domeme" in self.suppliers:
            fetchers["domeme"] = DomemeFetcher(
                self.storage,
                self.config.get("domeme", {})
            )
        
        # Ownerclan과 Zentrade는 증분 수집 미지원
        
        return fetchers
    
    def _init_transformers(self) -> Dict[str, Any]:
        """공급사별 Transformer 초기화"""
        transformers = {}
        
        if "domeme" in self.suppliers:
            transformers["domeme"] = DomemeTransformer()
        
        return transformers
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        return bool(self.fetchers)
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info("증분 수집 시작")
        
        stats = {
            "fetched": 0,
            "processed": 0,
            "failed": 0
        }
        
        # 조회 기간
        since = datetime.now() - timedelta(minutes=self.lookback_minutes)
        
        for supplier_name, fetcher in self.fetchers.items():
            try:
                # 최근 업데이트된 상품만 조회
                if hasattr(fetcher, 'fetch_updated_products'):
                    products = await fetcher.fetch_updated_products(
                        since=since,
                        limit=50
                    )
                    
                    stats["fetched"] += len(products)
                    
                    # 변환 및 저장
                    transformer = self.transformers[supplier_name]
                    
                    for product in products:
                        try:
                            standard_product = transformer.transform(product)
                            await self.storage.save_processed_product(
                                standard_product.dict()
                            )
                            stats["processed"] += 1
                            
                        except Exception as e:
                            logger.error(f"상품 처리 실패: {str(e)}")
                            stats["failed"] += 1
                
            except Exception as e:
                logger.error(f"{supplier_name} 증분 수집 실패: {str(e)}")
        
        logger.info(
            f"증분 수집 완료: "
            f"수집 {stats['fetched']}개, "
            f"처리 {stats['processed']}개"
        )
        
        return stats