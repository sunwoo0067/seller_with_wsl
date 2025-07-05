"""
내부 판매 상품 동기화 모듈
마켓 API를 통해 내부 판매 상품 데이터를 DB에 스냅샷으로 동기화
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from loguru import logger

from dropshipping.storage.base import BaseStorage


class SalesSynchronizer:
    """내부 판매 상품 동기화"""

    def __init__(self, storage: BaseStorage):
        self.storage = storage

    async def sync_sales_data(self, lookback_days: int = 30):
        """
        지정된 기간 동안의 판매 데이터를 동기화합니다.

        Args:
            lookback_days: 과거 몇 일까지의 데이터를 동기화할지 지정합니다.
        """
        logger.info(f"{lookback_days}일간의 판매 데이터 동기화 시작")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        # 모든 주문 데이터 가져오기
        orders = await self.storage.list(
            "orders", filters={"order_date": {"$gte": start_date, "$lte": end_date}}
        )

        if not orders:
            logger.info("동기화할 판매 데이터가 없습니다.")
            return

        # 판매 상품 데이터 집계 및 저장
        sales_records = self._aggregate_sales_from_orders(orders)
        await self._save_sales_records(sales_records)

        logger.info(f"판매 데이터 동기화 완료. {len(sales_records)}개 상품 업데이트.")

    def _aggregate_sales_from_orders(
        self, orders: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """주문 데이터로부터 판매 상품 데이터를 집계합니다."""
        aggregated_sales = {}

        for order in orders:
            order_date = order["order_date"]
            marketplace_id = order["marketplace_id"]
            account_id = order["account_id"]

            for item in order.get("items", []):
                product_id = item.get("product_id")
                if not product_id:
                    continue

                # 상품 정보 조회 (캐시 또는 DB)
                product = self.storage.get_processed_product(
                    product_id
                )  # StandardProduct 객체 반환
                if not product:
                    logger.warning(f"상품 정보를 찾을 수 없습니다: {product_id}")
                    continue

                key = f"{product.id}-{marketplace_id}-{account_id}"
                if key not in aggregated_sales:
                    aggregated_sales[key] = {
                        "product_id": product.id,
                        "marketplace_id": marketplace_id,
                        "account_id": account_id,
                        "total_sales_quantity": 0,
                        "total_sales_revenue": Decimal("0"),
                        "last_sale_date": datetime.min,
                        "first_sale_date": datetime.max,
                        "product_snapshot": product.model_dump_json(),  # 상품 스냅샷 저장
                    }

                aggregated_sales[key]["total_sales_quantity"] += item.get("quantity", 0)
                aggregated_sales[key]["total_sales_revenue"] += Decimal(
                    str(item.get("total_amount", 0))
                )
                aggregated_sales[key]["last_sale_date"] = max(
                    aggregated_sales[key]["last_sale_date"], order_date
                )
                aggregated_sales[key]["first_sale_date"] = min(
                    aggregated_sales[key]["first_sale_date"], order_date
                )

        return aggregated_sales

    async def _save_sales_records(self, sales_records: Dict[str, Dict[str, Any]]):
        """집계된 판매 기록을 DB에 저장합니다."""
        records_to_save = []
        for key, data in sales_records.items():
            # Decimal을 float으로 변환 (Supabase JSONB 호환)
            data["total_sales_revenue"] = float(data["total_sales_revenue"])
            data["last_sale_date"] = data["last_sale_date"].isoformat()
            data["first_sale_date"] = data["first_sale_date"].isoformat()
            records_to_save.append(data)

        if records_to_save:
            # upsert를 사용하여 기존 레코드를 업데이트하거나 새로 생성
            await self.storage.upsert(
                "sales_products",
                records_to_save,
                on_conflict="product_id,marketplace_id,account_id",
            )
            logger.info(
                f"{len(records_to_save)}개의 판매 기록을 sales_products 테이블에 저장/업데이트했습니다."
            )
        else:
            logger.info("저장할 판매 기록이 없습니다.")
