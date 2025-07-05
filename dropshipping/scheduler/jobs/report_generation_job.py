"""
리포트 생성 작업
일일/주간/월간 리포트 자동 생성
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import json
import csv
from io import StringIO

from loguru import logger

from dropshipping.scheduler.base import BaseJob, JobPriority
from dropshipping.storage.base import BaseStorage
from dropshipping.sourcing.dashboard import SourcingDashboard


class ReportGenerationJob(BaseJob):
    """리포트 생성 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("report_generation", storage, config)
        
        # 우선순위 낮음
        self.priority = JobPriority.LOW
        
        # 리포트 설정
        self.report_type = self.config.get("report_type", "daily")  # daily/weekly/monthly
        self.report_formats = self.config.get("formats", ["json", "csv"])
        self.include_sections = self.config.get("sections", [
            "sales", "inventory", "orders", "pricing", "sourcing", "alerts"
        ])
        self.send_email = self.config.get("send_email", True)
        self.email_recipients = self.config.get("email_recipients", [])
        
        # 소싱 대시보드
        self.sourcing_dashboard = SourcingDashboard(storage, config)
        
        # 통계
        self.stats = {
            "sections_generated": 0,
            "formats_created": 0,
            "emails_sent": 0
        }
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        # 이미 생성된 리포트 확인
        existing_report = await self.storage.get(
            "reports",
            filters={
                "type": self.report_type,
                "created_at": {
                    "$gte": self._get_report_start_date(),
                    "$lt": datetime.now()
                }
            }
        )
        
        if existing_report:
            logger.warning(f"{self.report_type} 리포트가 이미 생성되었습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info(f"{self.report_type} 리포트 생성 시작")
        
        # 리포트 기간 설정
        report_period = self._get_report_period()
        
        # 리포트 데이터 수집
        report_data = {
            "type": self.report_type,
            "period": {
                "start": report_period["start"],
                "end": report_period["end"]
            },
            "generated_at": datetime.now(),
            "sections": {}
        }
        
        # 섹션별 데이터 생성
        if "sales" in self.include_sections:
            report_data["sections"]["sales"] = await self._generate_sales_section(
                report_period["start"],
                report_period["end"]
            )
            self.stats["sections_generated"] += 1
        
        if "inventory" in self.include_sections:
            report_data["sections"]["inventory"] = await self._generate_inventory_section()
            self.stats["sections_generated"] += 1
        
        if "orders" in self.include_sections:
            report_data["sections"]["orders"] = await self._generate_orders_section(
                report_period["start"],
                report_period["end"]
            )
            self.stats["sections_generated"] += 1
        
        if "pricing" in self.include_sections:
            report_data["sections"]["pricing"] = await self._generate_pricing_section(
                report_period["start"],
                report_period["end"]
            )
            self.stats["sections_generated"] += 1
        
        if "sourcing" in self.include_sections:
            report_data["sections"]["sourcing"] = await self._generate_sourcing_section()
            self.stats["sections_generated"] += 1
        
        if "alerts" in self.include_sections:
            report_data["sections"]["alerts"] = await self._generate_alerts_section(
                report_period["start"],
                report_period["end"]
            )
            self.stats["sections_generated"] += 1
        
        # 리포트 요약 생성
        report_data["summary"] = self._generate_summary(report_data["sections"])
        
        # 리포트 저장
        saved_report = await self.storage.create("reports", report_data)
        
        # 다양한 형식으로 내보내기
        exported_files = await self._export_report(report_data)
        
        # 이메일 발송
        if self.send_email and self.email_recipients:
            await self._send_report_email(report_data, exported_files)
        
        # 결과 요약
        self.result = {
            "report_id": saved_report["id"],
            "stats": self.stats,
            "exported_files": exported_files,
            "completion_time": datetime.now()
        }
        
        logger.info(
            f"{self.report_type} 리포트 생성 완료: "
            f"섹션 {self.stats['sections_generated']}개, "
            f"형식 {self.stats['formats_created']}개"
        )
        
        return self.result
    
    def _get_report_period(self) -> Dict[str, datetime]:
        """리포트 기간 계산"""
        now = datetime.now()
        
        if self.report_type == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif self.report_type == "weekly":
            # 월요일 시작
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        else:  # monthly
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        
        return {"start": start, "end": end}
    
    def _get_report_start_date(self) -> datetime:
        """리포트 시작 날짜"""
        period = self._get_report_period()
        return period["start"]
    
    async def _generate_sales_section(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """판매 섹션 생성"""
        # 주문 데이터 조회
        orders = await self.storage.list(
            "orders",
            filters={
                "order_date": {
                    "$gte": start_date,
                    "$lte": end_date
                },
                "status": {"$in": ["delivered", "shipping", "in_transit"]}
            }
        )
        
        # 판매 통계 계산
        total_revenue = Decimal("0")
        total_orders = len(orders)
        total_items = 0
        product_sales = {}
        category_sales = {}
        marketplace_sales = {}
        
        for order in orders:
            # 매출 계산
            order_total = Decimal(str(order.get("total_amount", 0)))
            total_revenue += order_total
            
            # 마켓플레이스별 매출
            marketplace = order.get("marketplace", "unknown")
            if marketplace not in marketplace_sales:
                marketplace_sales[marketplace] = {
                    "revenue": Decimal("0"),
                    "orders": 0
                }
            marketplace_sales[marketplace]["revenue"] += order_total
            marketplace_sales[marketplace]["orders"] += 1
            
            # 상품별 판매
            for item in order.get("items", []):
                total_items += item.get("quantity", 0)
                
                product_id = item.get("product_id")
                if product_id:
                    if product_id not in product_sales:
                        product_sales[product_id] = {
                            "quantity": 0,
                            "revenue": Decimal("0")
                        }
                    product_sales[product_id]["quantity"] += item.get("quantity", 0)
                    product_sales[product_id]["revenue"] += Decimal(str(item.get("total_price", 0)))
                    
                    # 카테고리별 매출
                    product = await self.storage.get("products", product_id)
                    if product:
                        category = product.get("category_name", "기타")
                        if category not in category_sales:
                            category_sales[category] = {
                                "revenue": Decimal("0"),
                                "items": 0
                            }
                        category_sales[category]["revenue"] += Decimal(str(item.get("total_price", 0)))
                        category_sales[category]["items"] += item.get("quantity", 0)
        
        # 베스트셀러 상위 10개
        best_sellers = sorted(
            [
                {
                    "product_id": pid,
                    "quantity": data["quantity"],
                    "revenue": float(data["revenue"])
                }
                for pid, data in product_sales.items()
            ],
            key=lambda x: x["quantity"],
            reverse=True
        )[:10]
        
        # 베스트셀러 상품 정보 추가
        for item in best_sellers:
            product = await self.storage.get("products", item["product_id"])
            if product:
                item["product_name"] = product["name"]
                item["category"] = product.get("category_name", "기타")
        
        return {
            "total_revenue": float(total_revenue),
            "total_orders": total_orders,
            "total_items": total_items,
            "average_order_value": float(total_revenue / total_orders) if total_orders > 0 else 0,
            "best_sellers": best_sellers,
            "category_breakdown": {
                cat: {
                    "revenue": float(data["revenue"]),
                    "items": data["items"],
                    "percentage": float(data["revenue"] / total_revenue * 100) if total_revenue > 0 else 0
                }
                for cat, data in category_sales.items()
            },
            "marketplace_breakdown": {
                mp: {
                    "revenue": float(data["revenue"]),
                    "orders": data["orders"],
                    "percentage": float(data["revenue"] / total_revenue * 100) if total_revenue > 0 else 0
                }
                for mp, data in marketplace_sales.items()
            }
        }
    
    async def _generate_inventory_section(self) -> Dict[str, Any]:
        """재고 섹션 생성"""
        # 활성 상품 재고 현황
        active_products = await self.storage.list(
            "products",
            filters={"status": "active"}
        )
        
        total_products = len(active_products)
        total_stock_value = Decimal("0")
        low_stock_products = []
        out_of_stock_products = []
        category_stock = {}
        
        for product in active_products:
            stock = product.get("stock", 0)
            price = Decimal(str(product.get("base_price", 0)))
            stock_value = stock * price
            total_stock_value += stock_value
            
            # 카테고리별 재고
            category = product.get("category_name", "기타")
            if category not in category_stock:
                category_stock[category] = {
                    "products": 0,
                    "total_stock": 0,
                    "stock_value": Decimal("0")
                }
            category_stock[category]["products"] += 1
            category_stock[category]["total_stock"] += stock
            category_stock[category]["stock_value"] += stock_value
            
            # 재고 부족/품절 상품
            if stock == 0:
                out_of_stock_products.append({
                    "id": product["id"],
                    "name": product["name"],
                    "category": category
                })
            elif stock < 10:  # 재고 부족 기준
                low_stock_products.append({
                    "id": product["id"],
                    "name": product["name"],
                    "category": category,
                    "stock": stock
                })
        
        return {
            "total_products": total_products,
            "total_stock_value": float(total_stock_value),
            "out_of_stock_count": len(out_of_stock_products),
            "low_stock_count": len(low_stock_products),
            "out_of_stock_products": out_of_stock_products[:10],  # 상위 10개
            "low_stock_products": low_stock_products[:10],  # 상위 10개
            "category_breakdown": {
                cat: {
                    "products": data["products"],
                    "total_stock": data["total_stock"],
                    "stock_value": float(data["stock_value"])
                }
                for cat, data in category_stock.items()
            }
        }
    
    async def _generate_orders_section(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """주문 섹션 생성"""
        # 기간내 주문 조회
        orders = await self.storage.list(
            "orders",
            filters={
                "order_date": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
        )
        
        # 상태별 분류
        status_breakdown = {}
        sync_status_breakdown = {}
        marketplace_orders = {}
        hourly_distribution = {str(i): 0 for i in range(24)}
        
        for order in orders:
            # 주문 상태
            status = order.get("status", "unknown")
            if status not in status_breakdown:
                status_breakdown[status] = 0
            status_breakdown[status] += 1
            
            # 동기화 상태
            sync_status = order.get("sync_status", "unknown")
            if sync_status not in sync_status_breakdown:
                sync_status_breakdown[sync_status] = 0
            sync_status_breakdown[sync_status] += 1
            
            # 마켓플레이스별
            marketplace = order.get("marketplace", "unknown")
            if marketplace not in marketplace_orders:
                marketplace_orders[marketplace] = 0
            marketplace_orders[marketplace] += 1
            
            # 시간대별 분포
            order_hour = order["order_date"].hour
            hourly_distribution[str(order_hour)] += 1
        
        # 처리 시간 분석
        processing_times = []
        for order in orders:
            if order.get("forwarded_at") and order.get("order_date"):
                processing_time = (order["forwarded_at"] - order["order_date"]).total_seconds() / 3600
                processing_times.append(processing_time)
        
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        return {
            "total_orders": len(orders),
            "status_breakdown": status_breakdown,
            "sync_status_breakdown": sync_status_breakdown,
            "marketplace_breakdown": marketplace_orders,
            "hourly_distribution": hourly_distribution,
            "processing_metrics": {
                "average_processing_hours": round(avg_processing_time, 2),
                "orders_processed": len(processing_times)
            }
        }
    
    async def _generate_pricing_section(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """가격 섹션 생성"""
        # 가격 조정 이력
        price_adjustments = await self.storage.list(
            "price_adjustments",
            filters={
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
        )
        
        total_adjustments = len(price_adjustments)
        price_increases = 0
        price_decreases = 0
        total_change_amount = Decimal("0")
        category_adjustments = {}
        
        for adjustment in price_adjustments:
            change_amount = Decimal(str(adjustment.get("change_amount", 0)))
            total_change_amount += change_amount
            
            if change_amount > 0:
                price_increases += 1
            elif change_amount < 0:
                price_decreases += 1
            
            # 상품 정보 조회
            product = await self.storage.get("products", adjustment["product_id"])
            if product:
                category = product.get("category_name", "기타")
                if category not in category_adjustments:
                    category_adjustments[category] = {
                        "count": 0,
                        "total_change": Decimal("0")
                    }
                category_adjustments[category]["count"] += 1
                category_adjustments[category]["total_change"] += change_amount
        
        return {
            "total_adjustments": total_adjustments,
            "price_increases": price_increases,
            "price_decreases": price_decreases,
            "average_change_amount": float(
                total_change_amount / total_adjustments
            ) if total_adjustments > 0 else 0,
            "category_breakdown": {
                cat: {
                    "adjustments": data["count"],
                    "average_change": float(data["total_change"] / data["count"])
                }
                for cat, data in category_adjustments.items()
            }
        }
    
    async def _generate_sourcing_section(self) -> Dict[str, Any]:
        """소싱 섹션 생성"""
        # 소싱 대시보드에서 데이터 가져오기
        overview = await self.sourcing_dashboard.get_overview()
        
        # 주요 지표만 추출
        return {
            "market_trends": overview.get("market_trends", {}),
            "opportunities": overview.get("opportunities", [])[:5],  # 상위 5개
            "competition_status": overview.get("competition_status", {}),
            "keyword_insights": overview.get("keyword_insights", {})
        }
    
    async def _generate_alerts_section(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """알림 섹션 생성"""
        # 기간내 알림 조회
        alerts = await self.storage.list(
            "alerts",
            filters={
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
        )
        
        # 유형별 분류
        alert_types = {}
        severity_breakdown = {}
        
        for alert in alerts:
            # 유형별
            alert_type = alert.get("type", "unknown")
            if alert_type not in alert_types:
                alert_types[alert_type] = 0
            alert_types[alert_type] += 1
            
            # 심각도별
            severity = alert.get("severity", "info")
            if severity not in severity_breakdown:
                severity_breakdown[severity] = 0
            severity_breakdown[severity] += 1
        
        # 중요 알림 추출
        critical_alerts = [
            {
                "type": alert["type"],
                "message": alert["message"],
                "created_at": alert["created_at"]
            }
            for alert in alerts
            if alert.get("severity") == "critical"
        ][:10]  # 최근 10개
        
        return {
            "total_alerts": len(alerts),
            "type_breakdown": alert_types,
            "severity_breakdown": severity_breakdown,
            "critical_alerts": critical_alerts
        }
    
    def _generate_summary(self, sections: Dict[str, Any]) -> Dict[str, Any]:
        """리포트 요약 생성"""
        summary = {
            "highlights": [],
            "metrics": {},
            "recommendations": []
        }
        
        # 판매 하이라이트
        if "sales" in sections:
            sales = sections["sales"]
            summary["metrics"]["total_revenue"] = sales["total_revenue"]
            summary["metrics"]["total_orders"] = sales["total_orders"]
            
            if sales["total_revenue"] > 0:
                summary["highlights"].append(
                    f"총 매출 {sales['total_revenue']:,.0f}원 달성"
                )
        
        # 재고 하이라이트
        if "inventory" in sections:
            inventory = sections["inventory"]
            
            if inventory["out_of_stock_count"] > 0:
                summary["highlights"].append(
                    f"품절 상품 {inventory['out_of_stock_count']}개 발생"
                )
                summary["recommendations"].append(
                    "품절 상품의 재입고 필요"
                )
        
        # 주문 하이라이트
        if "orders" in sections:
            orders = sections["orders"]
            sync_status = orders.get("sync_status_breakdown", {})
            
            if sync_status.get("failed", 0) > 0:
                summary["highlights"].append(
                    f"주문 동기화 실패 {sync_status['failed']}건"
                )
                summary["recommendations"].append(
                    "실패한 주문 수동 확인 필요"
                )
        
        # 가격 하이라이트
        if "pricing" in sections:
            pricing = sections["pricing"]
            
            if pricing["total_adjustments"] > 0:
                summary["highlights"].append(
                    f"가격 조정 {pricing['total_adjustments']}건 실행"
                )
        
        # 알림 하이라이트
        if "alerts" in sections:
            alerts = sections["alerts"]
            critical_count = alerts.get("severity_breakdown", {}).get("critical", 0)
            
            if critical_count > 0:
                summary["highlights"].append(
                    f"긴급 알림 {critical_count}건 발생"
                )
                summary["recommendations"].append(
                    "긴급 알림 즉시 확인 필요"
                )
        
        return summary
    
    async def _export_report(self, report_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """리포트 내보내기"""
        exported_files = []
        
        # JSON 형식
        if "json" in self.report_formats:
            json_content = json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
            
            filename = f"{self.report_type}_report_{datetime.now().strftime('%Y%m%d')}.json"
            
            # 파일 저장 (실제로는 S3나 로컬 파일시스템에 저장)
            exported_files.append({
                "format": "json",
                "filename": filename,
                "size": len(json_content)
            })
            
            self.stats["formats_created"] += 1
        
        # CSV 형식 (요약 데이터만)
        if "csv" in self.report_formats:
            csv_buffer = StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # 헤더
            csv_writer.writerow(["섹션", "지표", "값"])
            
            # 판매 데이터
            if "sales" in report_data["sections"]:
                sales = report_data["sections"]["sales"]
                csv_writer.writerow(["판매", "총 매출", sales["total_revenue"]])
                csv_writer.writerow(["판매", "총 주문", sales["total_orders"]])
                csv_writer.writerow(["판매", "평균 주문 가격", sales["average_order_value"]])
            
            # 재고 데이터
            if "inventory" in report_data["sections"]:
                inventory = report_data["sections"]["inventory"]
                csv_writer.writerow(["재고", "총 상품", inventory["total_products"]])
                csv_writer.writerow(["재고", "재고 가치", inventory["total_stock_value"]])
                csv_writer.writerow(["재고", "품절 상품", inventory["out_of_stock_count"]])
            
            csv_content = csv_buffer.getvalue()
            filename = f"{self.report_type}_report_{datetime.now().strftime('%Y%m%d')}.csv"
            
            exported_files.append({
                "format": "csv",
                "filename": filename,
                "size": len(csv_content)
            })
            
            self.stats["formats_created"] += 1
        
        return exported_files
    
    async def _send_report_email(
        self,
        report_data: Dict[str, Any],
        exported_files: List[Dict[str, str]]
    ):
        """리포트 이메일 발송"""
        # TODO: 이메일 발송 구현
        # - SMTP 설정
        # - HTML 템플릿 렌더링
        # - 첨부파일 추가
        
        logger.info(f"리포트 이메일 발송 예정 - 수신자: {len(self.email_recipients)}명")
        self.stats["emails_sent"] = len(self.email_recipients)


class CustomReportJob(BaseJob):
    """맞춤형 리포트 생성 작업"""
    
    def __init__(
        self,
        storage: BaseStorage,
        config: Dict[str, Any] = None
    ):
        super().__init__("custom_report", storage, config)
        
        # 우선순위 보통
        self.priority = JobPriority.NORMAL
        
        # 맞춤 설정
        self.report_name = self.config.get("name", "custom_report")
        self.query_config = self.config.get("query", {})
        self.output_format = self.config.get("format", "json")
    
    async def validate(self) -> bool:
        """작업 실행 전 검증"""
        if not self.query_config:
            logger.error("쿼리 설정이 없습니다")
            return False
        
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """작업 실행"""
        logger.info(f"맞춤형 리포트 생성: {self.report_name}")
        
        # 쿼리 실행
        report_data = await self._execute_custom_query()
        
        # 리포트 저장
        saved_report = await self.storage.create("reports", {
            "type": "custom",
            "name": self.report_name,
            "data": report_data,
            "created_at": datetime.now()
        })
        
        logger.info(f"맞춤형 리포트 생성 완료: {self.report_name}")
        
        return {
            "report_id": saved_report["id"],
            "row_count": len(report_data) if isinstance(report_data, list) else 1
        }
    
    async def _execute_custom_query(self) -> Any:
        """맞춤형 쿼리 실행"""
        # TODO: 쿼리 설정에 따라 데이터 조회
        # - 테이블 조인
        # - 필터링
        # - 집계
        
        return []