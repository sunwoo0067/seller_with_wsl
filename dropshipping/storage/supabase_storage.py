"""
Supabase 저장소 구현
PostgreSQL 기반 데이터 저장 및 관리
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from supabase import Client, create_client
from supabase.lib.client_options import ClientOptions

from dropshipping.config import settings
from dropshipping.models.product import ProductImage, ProductOption, StandardProduct
from dropshipping.storage.base import BaseStorage


class SupabaseStorage(BaseStorage):
    """Supabase 저장소 구현"""

    def __init__(self, url: Optional[str] = None, service_key: Optional[str] = None):
        """
        Args:
            url: Supabase 프로젝트 URL
            service_key: Supabase service role key
        """
        self.url = url or (settings.supabase.url if settings.supabase else None)
        self.service_key = service_key or (
            settings.supabase.service_role_key if settings.supabase else None
        )

        if not self.url or not self.service_key:
            raise ValueError("Supabase URL과 Service Key가 필요합니다")

        # Supabase 클라이언트 생성
        self.client: Client = create_client(
            self.url,
            self.service_key,
            options=ClientOptions(
                auto_refresh_token=False,  # Service role key는 갱신 불필요
                persist_session=False,
            ),
        )

        self.supplier_id_cache = {}
        self.marketplace_id_cache = {}

        logger.info(f"Supabase 저장소 초기화: {self.url}")

    def save_raw_product(self, raw_data: Dict[str, Any]) -> str:
        """원본 상품 데이터 저장"""
        try:
            # 공급사 ID 조회
            supplier_id = self._get_supplier_id(raw_data["supplier_id"])
            if not supplier_id:
                raise ValueError(f"공급사를 찾을 수 없습니다: {raw_data['supplier_id']}")

            # 데이터 준비
            record = {
                "supplier_id": supplier_id,
                "supplier_product_id": raw_data["supplier_product_id"],
                "raw_json": raw_data["raw_json"],
                "data_hash": raw_data["data_hash"],
                "fetched_at": raw_data.get("fetched_at", datetime.now()).isoformat(),
            }

            # 중복 체크 (upsert 사용)
            result = (
                self.client.table("products_raw")
                .upsert(record, on_conflict="supplier_id,data_hash")
                .execute()
            )

            if result.data:
                record_id = result.data[0]["id"]
                logger.debug(f"원본 상품 저장: {record_id}")
                return record_id
            else:
                raise ValueError("데이터 저장 실패")

        except Exception as e:
            logger.error(f"원본 상품 저장 실패: {str(e)}")
            raise

    def save_processed_product(self, raw_id: str, product: StandardProduct) -> str:
        """처리된 상품 데이터 저장"""
        try:
            # 공급사 ID 조회
            supplier_id = self._get_supplier_id(product.supplier_id)
            if not supplier_id:
                raise ValueError(f"공급사를 찾을 수 없습니다: {product.supplier_id}")

            # 데이터 준비
            record = {
                "raw_id": raw_id,
                "supplier_id": supplier_id,
                "supplier_product_id": product.supplier_product_id,
                "name": product.name,
                "brand": product.brand,
                "manufacturer": product.manufacturer,
                "origin": product.origin,
                "cost": float(product.cost),
                "price": float(product.price),
                "list_price": float(product.list_price) if product.list_price else None,
                "stock": product.stock,
                "status": (
                    product.status if isinstance(product.status, str) else product.status.value
                ),
                "category_code": product.category_code,
                "category_name": product.category_name,
                "category_path": product.category_path,
                "images": self._serialize_images(product.images),
                "options": self._serialize_options(product.options),
                "attributes": product.attributes,
            }

            # Upsert (중복시 업데이트)
            result = (
                self.client.table("products_processed")
                .upsert(record, on_conflict="supplier_id,supplier_product_id")
                .execute()
            )

            if result.data:
                product_id = result.data[0]["id"]
                logger.debug(f"처리된 상품 저장: {product_id}")

                # 변형 상품 저장
                if product.variants:
                    self._save_variants(product_id, product.variants)

                return product_id
            else:
                raise ValueError("데이터 저장 실패")

        except Exception as e:
            logger.error(f"처리된 상품 저장 실패: {str(e)}")
            raise

    def exists_by_hash(self, supplier_id: str, data_hash: str) -> bool:
        """해시로 중복 체크"""
        try:
            # 공급사 ID 조회
            supplier_uuid = self._get_supplier_id(supplier_id)
            if not supplier_uuid:
                return False

            result = (
                self.client.table("products_raw")
                .select("id")
                .eq("supplier_id", supplier_uuid)
                .eq("data_hash", data_hash)
                .execute()
            )

            return len(result.data) > 0

        except Exception as e:
            logger.error(f"중복 체크 실패: {str(e)}")
            return False

    def get_raw_product(self, record_id: str) -> Optional[Dict[str, Any]]:
        """원본 상품 데이터 조회"""
        try:
            result = (
                self.client.table("products_raw").select("*").eq("id", record_id).single().execute()
            )

            if result.data:
                return self._format_raw_product(result.data)
            return None

        except Exception as e:
            logger.error(f"원본 상품 조회 실패: {str(e)}")
            return None

    def get_processed_product(self, record_id: str) -> Optional[StandardProduct]:
        """처리된 상품 데이터 조회"""
        try:
            result = (
                self.client.table("products_processed")
                .select("*, product_variants(*)")
                .eq("id", record_id)
                .single()
                .execute()
            )

            if result.data:
                return self._deserialize_product(result.data)
            return None

        except Exception as e:
            logger.error(f"처리된 상품 조회 실패: {str(e)}")
            return None

    def list_raw_products(
        self,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """원본 상품 목록 조회"""
        try:
            query = self.client.table("products_raw").select("*")

            # 필터 적용
            if supplier_id:
                supplier_uuid = self._get_supplier_id(supplier_id)
                if supplier_uuid:
                    query = query.eq("supplier_id", supplier_uuid)

            # 정렬 및 페이징
            query = query.order("fetched_at", desc=True).range(offset, offset + limit - 1)

            result = query.execute()

            return [self._format_raw_product(record) for record in result.data]

        except Exception as e:
            logger.error(f"원본 상품 목록 조회 실패: {str(e)}")
            return []

    def update_status(self, record_id: str, status: str) -> bool:
        """상태 업데이트"""
        try:
            # products_processed 테이블의 상태 업데이트
            result = (
                self.client.table("products_processed")
                .update({"status": status})
                .eq("id", record_id)
                .execute()
            )

            return len(result.data) > 0

        except Exception as e:
            logger.error(f"상태 업데이트 실패: {str(e)}")
            return False

    def get_stats(self, supplier_id: Optional[str] = None) -> Dict[str, Any]:
        """통계 조회"""
        try:
            stats = {
                "total_raw": 0,
                "total_processed": 0,
                "by_status": {},
                "by_supplier": {},
            }

            # 원본 상품 통계
            raw_query = self.client.table("products_raw").select("supplier_id", count="exact")
            if supplier_id:
                supplier_uuid = self._get_supplier_id(supplier_id)
                if supplier_uuid:
                    raw_query = raw_query.eq("supplier_id", supplier_uuid)

            raw_result = raw_query.execute()
            stats["total_raw"] = raw_result.count

            # 처리된 상품 통계
            processed_query = self.client.table("products_processed").select(
                "supplier_id, status", count="exact"
            )
            if supplier_id and supplier_uuid:
                processed_query = processed_query.eq("supplier_id", supplier_uuid)

            processed_result = processed_query.execute()
            stats["total_processed"] = processed_result.count

            # 상태별 통계
            for record in processed_result.data:
                status = record["status"]
                if status not in stats["by_status"]:
                    stats["by_status"][status] = 0
                stats["by_status"][status] += 1

            # 공급사별 통계는 별도 쿼리로
            if not supplier_id:
                supplier_stats = (
                    self.client.table("products_processed").select("supplier_id").execute()
                )

                for record in supplier_stats.data:
                    sid = record["supplier_id"]
                    if sid not in stats["by_supplier"]:
                        stats["by_supplier"][sid] = {"raw": 0, "processed": 0}
                    stats["by_supplier"][sid]["processed"] += 1

            return stats

        except Exception as e:
            logger.error(f"통계 조회 실패: {str(e)}")
            return {}

    def _init_id_caches(self):
        """공급사 및 마켓플레이스 ID 캐시 초기화"""
        try:
            suppliers = self.client.table("suppliers").select("id, code").execute()
            for s in suppliers.data:
                self.supplier_id_cache[s["id"]] = s["code"]
                self.supplier_id_cache[s["code"]] = s["id"]

            marketplaces = self.client.table("marketplaces").select("id, code").execute()
            for m in marketplaces.data:
                self.marketplace_id_cache[m["id"]] = m["code"]
                self.marketplace_id_cache[m["code"]] = m["id"]
            logger.info("ID 캐시 초기화 완료")
        except Exception as e:
            logger.error(f"ID 캐시 초기화 실패: {e}")

    def _get_supplier_id(self, supplier_code: str) -> Optional[str]:
        """공급사 코드로 UUID 조회 (캐시 활용)"""
        if not self.supplier_id_cache:
            self._init_id_caches()
        return self.supplier_id_cache.get(supplier_code)

    def _get_supplier_code(self, supplier_id: str) -> str:
        """공급사 UUID로 코드 조회 (캐시 활용)"""
        if not self.supplier_id_cache:
            self._init_id_caches()
        return self.supplier_id_cache.get(supplier_id, supplier_id)

    def _get_marketplace_id(self, marketplace_code: str) -> Optional[str]:
        """마켓플레이스 코드로 UUID 조회 (캐시 활용)"""
        if not self.marketplace_id_cache:
            self._init_id_caches()
        return self.marketplace_id_cache.get(marketplace_code)

    def _get_marketplace_code(self, marketplace_id: str) -> str:
        """마켓플레이스 UUID로 코드 조회 (캐시 활용)"""
        if not self.marketplace_id_cache:
            self._init_id_caches()
        return self.marketplace_id_cache.get(marketplace_id, marketplace_id)

    def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        """모든 카테고리 매핑 정보 조회"""
        try:
            result = self.client.table("category_mappings").select("*").execute()
            return result.data
        except Exception as e:
            logger.error(f"전체 카테고리 매핑 조회 실패: {str(e)}")
            return []

    def _serialize_images(self, images: List[ProductImage]) -> List[Dict[str, Any]]:
        """이미지 객체를 JSON으로 변환"""
        return [
            {
                "url": str(img.url),
                "alt": img.alt,
                "is_main": img.is_main,
                "order": img.order,
                "width": img.width,
                "height": img.height,
                "size": img.size,
            }
            for img in images
        ]

    def _serialize_options(self, options: List[ProductOption]) -> List[Dict[str, Any]]:
        """옵션 객체를 JSON으로 변환"""
        return [
            {
                "name": opt.name,
                "type": opt.type if isinstance(opt.type, str) else opt.type.value,
                "values": opt.values,
                "required": opt.required,
            }
            for opt in options
        ]

    def _format_raw_product(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """원본 상품 레코드 포맷팅"""
        return {
            "id": record["id"],
            "supplier_id": self._get_supplier_code(record["supplier_id"]),
            "supplier_product_id": record["supplier_product_id"],
            "raw_json": record["raw_json"],
            "data_hash": record["data_hash"],
            "fetched_at": record["fetched_at"],
            "created_at": record["created_at"],
        }

    def _deserialize_product(self, record: Dict[str, Any]) -> StandardProduct:
        """데이터베이스 레코드를 StandardProduct로 변환"""
        # 이미지 역직렬화
        images = []
        if record.get("images"):
            for img_data in record["images"]:
                images.append(ProductImage(**img_data))

        # 옵션 역직렬화
        options = []
        if record.get("options"):
            for opt_data in record["options"]:
                options.append(ProductOption(**opt_data))

        # StandardProduct 생성
        return StandardProduct(
            id=record["id"],
            supplier_id=self._get_supplier_code(record["supplier_id"]),
            supplier_product_id=record["supplier_product_id"],
            name=record["name"],
            brand=record.get("brand"),
            manufacturer=record.get("manufacturer"),
            origin=record.get("origin"),
            cost=Decimal(str(record["cost"])),
            price=Decimal(str(record["price"])),
            list_price=Decimal(str(record["list_price"])) if record.get("list_price") else None,
            stock=record.get("stock", 0),
            status=record["status"],
            category_code=record.get("category_code"),
            category_name=record.get("category_name"),
            category_path=record.get("category_path"),
            images=images,
            options=options,
            attributes=record.get("attributes", {}),
        )

    def _save_variants(self, product_id: str, variants: List[Dict[str, Any]]):
        """변형 상품 저장"""
        try:
            variant_records = []
            for variant in variants:
                variant_records.append(
                    {
                        "product_id": product_id,
                        "sku": variant["sku"],
                        "option_values": variant["option_values"],
                        "additional_cost": float(variant.get("additional_cost", 0)),
                        "stock": variant.get("stock", 0),
                        "is_active": variant.get("is_active", True),
                    }
                )

            if variant_records:
                self.client.table("product_variants").upsert(
                    variant_records, on_conflict="sku"
                ).execute()

        except Exception as e:
            logger.error(f"변형 상품 저장 실패: {str(e)}")

    # === 추가 메서드 ===

    def get_pricing_rules(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """가격 책정 규칙 조회"""
        try:
            query = self.client.table("pricing_rules").select("*")

            if active_only:
                query = query.eq("is_active", True)

            query = query.order("priority", desc=True)
            result = query.execute()

            return result.data

        except Exception as e:
            logger.error(f"가격 규칙 조회 실패: {str(e)}")
            return []

    def get_category_mappings(self, supplier_id: str, marketplace_id: str) -> List[Dict[str, Any]]:
        """카테고리 매핑 조회"""
        try:
            supplier_uuid = self._get_supplier_id(supplier_id)
            marketplace_uuid = self._get_marketplace_id(marketplace_id)

            if not supplier_uuid or not marketplace_uuid:
                return []

            result = (
                self.client.table("category_mappings")
                .select("*")
                .eq("supplier_id", supplier_uuid)
                .eq("marketplace_id", marketplace_uuid)
                .execute()
            )

            return result.data

        except Exception as e:
            logger.error(f"카테고리 매핑 조회 실패: {str(e)}")
            return []

    def log_pipeline(
        self,
        pipeline_type: str,
        target_type: str,
        target_id: str,
        status: str = "running",
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """파이프라인 실행 로그 기록"""
        try:
            record = {
                "pipeline_type": pipeline_type,
                "target_type": target_type,
                "target_id": target_id,
                "status": status,
                "started_at": datetime.now().isoformat(),
                "details": details or {},
            }

            result = self.client.table("pipeline_logs").insert(record).execute()

            if result.data:
                return result.data[0]["id"]
            return ""

        except Exception as e:
            logger.error(f"파이프라인 로그 기록 실패: {str(e)}")
            return ""

    def update_pipeline_log(
        self,
        log_id: str,
        status: str,
        records_processed: int = 0,
        records_failed: int = 0,
        error_message: Optional[str] = None,
    ):
        """파이프라인 로그 업데이트"""
        try:
            update_data = {
                "status": status,
                "completed_at": datetime.now().isoformat(),
                "records_processed": records_processed,
                "records_failed": records_failed,
            }

            if error_message:
                update_data["error_message"] = error_message

            self.client.table("pipeline_logs").update(update_data).eq("id", log_id).execute()

        except Exception as e:
            logger.error(f"파이프라인 로그 업데이트 실패: {str(e)}")

    async def upsert(
        self, table_name: str, records: List[Dict[str, Any]], on_conflict: str
    ) -> List[Dict[str, Any]]:
        """레코드를 삽입하거나 업데이트합니다."""
        try:
            result = (
                self.client.table(table_name).upsert(records, on_conflict=on_conflict).execute()
            )
            if result.data:
                logger.debug(f"Upserted {len(result.data)} records into {table_name}")
                return result.data
            else:
                logger.warning(f"No records upserted into {table_name}")
                return []
        except Exception as e:
            logger.error(f"Upsert failed for table {table_name}: {str(e)}")
            raise

    def get_marketplace_upload(self, product_id: str, marketplace_id: str) -> Optional[Dict[str, Any]]:
        """마켓플레이스 업로드 기록을 조회합니다."""
        try:
            marketplace_uuid = self._get_marketplace_id(marketplace_id)
            if not marketplace_uuid:
                return None

            result = (
                self.client.table("marketplace_uploads")
                .select("*")
                .eq("processed_product_id", product_id)
                .eq("marketplace_id", marketplace_uuid)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"마켓플레이스 업로드 기록 조회 실패: {str(e)}")
            return None

    def save_marketplace_upload(self, record: Dict[str, Any]):
        """마켓플레이스 업로드 기록을 저장합니다."""
        try:
            # Upsert를 사용하여 존재하면 업데이트, 없으면 삽입
            result = (
                self.client.table("marketplace_uploads")
                .upsert(record, on_conflict="processed_product_id,marketplace_id")
                .execute()
            )
            if not result.data:
                raise ValueError("마켓플레이스 업로드 기록 저장 실패")
            logger.debug(f"마켓플레이스 업로드 기록 저장: {result.data[0]['id']}")
        except Exception as e:
            logger.error(f"마켓플레이스 업로드 기록 저장 실패: {str(e)}")
            raise

    def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        """모든 카테고리 매핑 정보를 조회합니다."""
        try:
            result = self.client.table("category_mappings").select("*").execute()
            return result.data
        except Exception as e:
            logger.error(f"전체 카테고리 매핑 조회 실패: {str(e)}")
            return []

    def get_supplier_code(self, supplier_id: str) -> str:
        """공급사 ID로 코드를 조회합니다."""
        # Check cache first
        for code, uuid in self.supplier_id_cache.items():
            if uuid == supplier_id:
                return code
        
        try:
            result = self.client.table("suppliers").select("code").eq("id", supplier_id).single().execute()
            if result.data:
                code = result.data['code']
                self.supplier_id_cache[code] = supplier_id # Update cache
                return code
            raise ValueError(f"Supplier with ID {supplier_id} not found.")
        except Exception as e:
            logger.error(f"공급사 코드 조회 실패: {str(e)}")
            raise

    def get_marketplace_code(self, marketplace_id: str) -> str:
        """마켓플레이스 ID로 코드를 조회합니다."""
        # Check cache first
        for code, uuid in self.marketplace_id_cache.items():
            if uuid == marketplace_id:
                return code
        
        try:
            result = self.client.table("marketplaces").select("code").eq("id", marketplace_id).single().execute()
            if result.data:
                code = result.data['code']
                self.marketplace_id_cache[code] = marketplace_id # Update cache
                return code
            raise ValueError(f"Marketplace with ID {marketplace_id} not found.")
        except Exception as e:
            logger.error(f"마켓플레이스 코드 조회 실패: {str(e)}")
            raise
