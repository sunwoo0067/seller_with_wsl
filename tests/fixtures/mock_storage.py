"""
테스트용 Mock Storage 구현
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
import asyncio

from dropshipping.storage.base import BaseStorage
from dropshipping.models.product import StandardProduct


class MockStorage(BaseStorage):
    """테스트용 Mock Storage"""
    
    def __init__(self):
        super().__init__()
        self.data = {}
        self.id_counter = 1
        self._lock = asyncio.Lock()
    
    async def create(self, table: str, data: dict) -> dict:
        """데이터 생성"""
        if table not in self.data:
            self.data[table] = {}
        
        id_val = str(self.id_counter)
        self.id_counter += 1
        
        self.data[table][id_val] = {
            "id": id_val,
            **data,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        return self.data[table][id_val]
    
    async def read(self, table: str, id_val: str) -> Optional[dict]:
        """데이터 읽기"""
        if table not in self.data or id_val not in self.data[table]:
            return None
        return self.data[table][id_val]
    
    async def get(self, table: str, id: str = None, filters: dict = None) -> Optional[dict]:
        """데이터 조회 (read의 별칭)"""
        if id:
            return await self.read(table, id)
        
        if filters:
            items = await self.list(table, filters, limit=1)
            return items[0] if items else None
        
        return None
    
    async def update(self, table: str, id_val: str, data: dict) -> Optional[dict]:
        """데이터 업데이트"""
        if table not in self.data or id_val not in self.data[table]:
            return None
        
        self.data[table][id_val].update(data)
        self.data[table][id_val]["updated_at"] = datetime.now()
        return self.data[table][id_val]
    
    async def delete(self, table: str, id_val: str) -> bool:
        """데이터 삭제"""
        if table not in self.data or id_val not in self.data[table]:
            return False
        
        del self.data[table][id_val]
        return True
    
    async def list(self, table: str, filters: Optional[dict] = None, limit: int = 100) -> List[dict]:
        """데이터 목록 조회"""
        if table not in self.data:
            return []
        
        items = list(self.data[table].values())
        
        if filters:
            # 간단한 필터링 구현
            filtered = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if key not in item or item[key] != value:
                        match = False
                        break
                if match:
                    filtered.append(item)
            items = filtered
        
        return items[:limit]
    
    # BaseStorage 추상 메서드 구현
    
    def save_raw_product(self, raw_data: Dict[str, Any]) -> str:
        """원본 상품 데이터 저장"""
        result = asyncio.run(self.create("raw_products", raw_data))
        return result["id"]
    
    def save_processed_product(self, raw_id: str, product: StandardProduct) -> str:
        """처리된 상품 데이터 저장"""
        data = product.dict() if hasattr(product, 'dict') else product
        data["raw_id"] = raw_id
        result = asyncio.run(self.create("processed_products", data))
        return result["id"]
    
    def exists_by_hash(self, supplier_id: str, data_hash: str) -> bool:
        """해시로 중복 체크"""
        items = asyncio.run(self.list("raw_products", {
            "supplier_id": supplier_id,
            "data_hash": data_hash
        }))
        return len(items) > 0
    
    def get_raw_product(self, raw_id: str) -> Optional[Dict[str, Any]]:
        """원본 상품 조회"""
        return asyncio.run(self.read("raw_products", raw_id))
    
    def get_processed_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """처리된 상품 조회"""
        return asyncio.run(self.read("processed_products", product_id))
    
    def list_raw_products(
        self,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """원본 상품 목록 조회"""
        filters = {}
        if supplier_id:
            filters["supplier_id"] = supplier_id
        if status:
            filters["status"] = status
            
        items = asyncio.run(self.list("raw_products", filters, limit + offset))
        return items[offset:offset + limit]
    
    def update_status(self, table: str, id_val: str, status: str) -> bool:
        """상태 업데이트"""
        result = asyncio.run(self.update(table, id_val, {"status": status}))
        return result is not None
    
    def get_stats(self, table: str, group_by: Optional[str] = None) -> Dict[str, Any]:
        """통계 조회"""
        items = asyncio.run(self.list(table))
        
        stats = {
            "total": len(items),
            "by_status": {}
        }
        
        if group_by == "status":
            for item in items:
                status = item.get("status", "unknown")
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        
        return stats
    
    def upsert(
        self,
        table: str,
        data: Dict[str, Any],
        unique_fields: List[str]
    ) -> str:
        """데이터 업서트"""
        # 기존 데이터 찾기
        items = asyncio.run(self.list(table))
        
        for item in items:
            match = True
            for field in unique_fields:
                if item.get(field) != data.get(field):
                    match = False
                    break
            
            if match:
                # 업데이트
                result = asyncio.run(self.update(table, item["id"], data))
                return result["id"]
        
        # 새로 생성
        result = asyncio.run(self.create(table, data))
        return result["id"]
    
    def get_marketplace_upload(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """마켓플레이스 업로드 조회"""
        return asyncio.run(self.read("marketplace_uploads", upload_id))
    
    def save_marketplace_upload(self, upload_data: Dict[str, Any]) -> str:
        """마켓플레이스 업로드 저장"""
        result = asyncio.run(self.create("marketplace_uploads", upload_data))
        return result["id"]
    
    def get_pricing_rules(self) -> List[Dict[str, Any]]:
        """가격 규칙 조회"""
        return asyncio.run(self.list("pricing_rules"))
    
    def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        """카테고리 매핑 조회"""
        return asyncio.run(self.list("category_mappings"))
    
    def get_supplier_code(self, supplier_name: str) -> str:
        """공급사 코드 조회"""
        return f"{supplier_name.upper()}_001"
    
    def get_marketplace_code(self, marketplace_name: str) -> str:
        """마켓플레이스 코드 조회"""
        return f"{marketplace_name.upper()}_001"