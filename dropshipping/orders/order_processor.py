"""
주문 통합 프로세서
마켓플레이스 주문을 수집하고 공급사에 전달하는 통합 시스템
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger

from dropshipping.models.order import Order, OrderStatus
from dropshipping.orders.base import BaseOrderManager, OrderManagerType
from dropshipping.orders.coupang.coupang_order_manager import CoupangOrderManager
from dropshipping.orders.elevenst.elevenst_order_manager import ElevenstOrderManager
from dropshipping.orders.naver.smartstore_order_manager import SmartstoreOrderManager
from dropshipping.orders.supplier.base import BaseSupplierOrderer, SupplierType
from dropshipping.orders.supplier.domeme_orderer import DomemeOrderer
from dropshipping.storage.base import BaseStorage


class OrderProcessor:
    """주문 통합 처리기"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 전체 설정
        """
        self.storage = storage
        self.config = config or {}

        # 마켓플레이스 주문 관리자 초기화
        self.order_managers: Dict[str, BaseOrderManager] = {}
        self._init_order_managers()

        # 공급사 주문 전달자 초기화
        self.supplier_orderers: Dict[str, BaseSupplierOrderer] = {}
        self._init_supplier_orderers()

    def _init_order_managers(self):
        """마켓플레이스 주문 관리자 초기화"""
        # 쿠팡
        if self.config.get("coupang", {}).get("enabled", False):
            self.order_managers["coupang"] = CoupangOrderManager(
                storage=self.storage, config=self.config.get("coupang", {})
            )
            logger.info("쿠팡 주문 관리자 초기화 완료")

        # 11번가
        if self.config.get("elevenst", {}).get("enabled", False):
            self.order_managers["elevenst"] = ElevenstOrderManager(
                storage=self.storage, config=self.config.get("elevenst", {})
            )
            logger.info("11번가 주문 관리자 초기화 완료")

        # 스마트스토어
        if self.config.get("smartstore", {}).get("enabled", False):
            self.order_managers["smartstore"] = SmartstoreOrderManager(
                storage=self.storage, config=self.config.get("smartstore", {})
            )
            logger.info("스마트스토어 주문 관리자 초기화 완료")

    def _init_supplier_orderers(self):
        """공급사 주문 전달자 초기화"""
        # 도매매
        if self.config.get("domeme", {}).get("enabled", False):
            self.supplier_orderers["domeme"] = DomemeOrderer(
                storage=self.storage, config=self.config.get("domeme", {})
            )
            logger.info("도매매 주문 전달자 초기화 완료")

    async def process_new_orders(self) -> Dict[str, int]:
        """
        새로운 주문 처리

        Returns:
            처리 결과 (마켓플레이스별 처리된 주문 수)
        """
        results = {}

        # 1. 각 마켓플레이스에서 신규 주문 수집
        all_orders = []
        for marketplace_name, manager in self.order_managers.items():
            try:
                # 최근 1일간 주문 조회
                start_date = datetime.now() - timedelta(days=1)
                orders = await manager.fetch_orders(start_date)

                logger.info(f"{marketplace_name}에서 {len(orders)} 건의 주문 수집")

                # 주문 데이터 변환 및 저장
                for raw_order in orders:
                    order = await manager.transform_order(raw_order)
                    saved_order = await self.storage.save_order(order)
                    all_orders.append(saved_order)

                results[marketplace_name] = len(orders)

            except Exception as e:
                logger.error(f"{marketplace_name} 주문 수집 실패: {str(e)}")
                results[marketplace_name] = 0

        # 2. 수집된 주문을 공급사별로 그룹화
        supplier_orders = await self._group_orders_by_supplier(all_orders)

        # 3. 각 공급사에 주문 전달
        for supplier_name, orders in supplier_orders.items():
            if supplier_name in self.supplier_orderers:
                orderer = self.supplier_orderers[supplier_name]
                try:
                    for order in orders:
                        # 공급사에 주문 전달
                        supplier_order_id = await orderer.place_order(order)

                        # 주문 상태 업데이트
                        order.supplier_order_id = supplier_order_id
                        order.supplier_ordered_at = datetime.now()
                        await self.storage.update_order(order)

                        logger.info(
                            f"주문 {order.id}를 {supplier_name}에 전달 완료 "
                            f"(공급사 주문번호: {supplier_order_id})"
                        )

                except Exception as e:
                    logger.error(f"{supplier_name} 주문 전달 실패: {str(e)}")

        return results

    async def _group_orders_by_supplier(self, orders: List[Order]) -> Dict[str, List[Order]]:
        """
        주문을 공급사별로 그룹화

        Args:
            orders: 주문 목록

        Returns:
            공급사별 주문 딕셔너리
        """
        supplier_orders = {}

        for order in orders:
            # 주문 항목별로 공급사 확인
            for item in order.items:
                # 상품 정보에서 공급사 확인
                product = await self.storage.get_product(item.product_id)
                if product and product.get("supplier_id"):
                    supplier_id = product["supplier_id"]

                    if supplier_id not in supplier_orders:
                        supplier_orders[supplier_id] = []

                    # 동일 주문이 이미 추가되지 않았다면 추가
                    if order not in supplier_orders[supplier_id]:
                        supplier_orders[supplier_id].append(order)

        return supplier_orders

    async def sync_order_status(self) -> Dict[str, int]:
        """
        주문 상태 동기화

        Returns:
            처리 결과 (상태별 업데이트된 주문 수)
        """
        results = {"updated": 0, "failed": 0}

        # 진행중인 주문 조회
        active_orders = await self.storage.get_active_orders()

        for order in active_orders:
            try:
                # 마켓플레이스 주문 상태 확인
                if order.marketplace in self.order_managers:
                    manager = self.order_managers[order.marketplace]
                    updated_order = await manager.fetch_order_detail(order.marketplace_order_id)

                    if updated_order:
                        # 상태 업데이트
                        transformed = await manager.transform_order(updated_order)
                        order.status = transformed.status
                        order.delivery = transformed.delivery
                        await self.storage.update_order(order)
                        results["updated"] += 1

                # 공급사 주문 상태 확인
                if order.supplier_order_id:
                    supplier_id = await self._get_supplier_from_order(order)
                    if supplier_id in self.supplier_orderers:
                        orderer = self.supplier_orderers[supplier_id]
                        supplier_status = await orderer.check_order_status(order.supplier_order_id)

                        if supplier_status:
                            order.supplier_order_status = supplier_status
                            await self.storage.update_order(order)

            except Exception as e:
                logger.error(f"주문 {order.id} 상태 동기화 실패: {str(e)}")
                results["failed"] += 1

        return results

    async def _get_supplier_from_order(self, order: Order) -> Optional[str]:
        """주문에서 공급사 ID 추출"""
        if order.items:
            product = await self.storage.get_product(order.items[0].product_id)
            if product:
                return product.get("supplier_id")
        return None

    async def update_tracking_info(self) -> Dict[str, int]:
        """
        배송 정보 업데이트

        Returns:
            처리 결과
        """
        results = {"updated": 0, "failed": 0}

        # 배송 준비중/배송중 주문 조회
        shipping_orders = await self.storage.get_orders_for_tracking()

        for order in shipping_orders:
            try:
                # 공급사에서 송장번호 조회
                if order.supplier_order_id:
                    supplier_id = await self._get_supplier_from_order(order)
                    if supplier_id in self.supplier_orderers:
                        orderer = self.supplier_orderers[supplier_id]
                        tracking_info = await orderer.get_tracking_info(order.supplier_order_id)

                        if tracking_info:
                            # 마켓플레이스에 송장 정보 전달
                            if order.marketplace in self.order_managers:
                                manager = self.order_managers[order.marketplace]
                                success = await manager.update_tracking_info(
                                    order.marketplace_order_id,
                                    tracking_info["carrier"],
                                    tracking_info["tracking_number"],
                                )

                                if success:
                                    order.delivery.carrier = tracking_info["carrier"]
                                    order.delivery.tracking_number = tracking_info[
                                        "tracking_number"
                                    ]
                                    await self.storage.update_order(order)
                                    results["updated"] += 1

            except Exception as e:
                logger.error(f"주문 {order.id} 배송 정보 업데이트 실패: {str(e)}")
                results["failed"] += 1

        return results

    async def process_cancellations(self) -> Dict[str, int]:
        """
        취소 요청 처리

        Returns:
            처리 결과
        """
        results = {"processed": 0, "failed": 0}

        # 취소 요청된 주문 조회
        cancelled_orders = await self.storage.get_cancelled_orders()

        for order in cancelled_orders:
            try:
                # 공급사 주문 취소
                if order.supplier_order_id:
                    supplier_id = await self._get_supplier_from_order(order)
                    if supplier_id in self.supplier_orderers:
                        orderer = self.supplier_orderers[supplier_id]
                        success = await orderer.cancel_order(order.supplier_order_id)

                        if success:
                            order.supplier_order_status = "cancelled"
                            await self.storage.update_order(order)
                            results["processed"] += 1

            except Exception as e:
                logger.error(f"주문 {order.id} 취소 처리 실패: {str(e)}")
                results["failed"] += 1

        return results
