"""
스케줄러 작업 모듈
다양한 자동화 작업 구현
"""

from dropshipping.scheduler.jobs.collection_job import (
    DailyCollectionJob,
    IncrementalCollectionJob
)
from dropshipping.scheduler.jobs.inventory_update_job import (
    InventoryUpdateJob,
    RealTimeInventoryJob
)
from dropshipping.scheduler.jobs.price_adjustment_job import (
    PriceAdjustmentJob,
    DynamicPricingJob
)
from dropshipping.scheduler.jobs.order_sync_job import (
    OrderSyncJob,
    OrderStatusCheckJob
)
from dropshipping.scheduler.jobs.report_generation_job import (
    ReportGenerationJob,
    CustomReportJob
)

__all__ = [
    # 수집 작업
    "DailyCollectionJob",
    "IncrementalCollectionJob",
    
    # 재고 업데이트
    "InventoryUpdateJob",
    "RealTimeInventoryJob",
    
    # 가격 조정
    "PriceAdjustmentJob",
    "DynamicPricingJob",
    
    # 주문 동기화
    "OrderSyncJob",
    "OrderStatusCheckJob",
    
    # 리포트 생성
    "ReportGenerationJob",
    "CustomReportJob"
]