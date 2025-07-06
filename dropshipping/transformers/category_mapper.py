from typing import Dict, List, Optional
from functools import lru_cache

from dropshipping.storage.supabase_storage import SupabaseStorage

class CategoryMapper:
    """
    공급사 카테고리 코드를 마켓플레이스 카테고리 코드로 매핑하는 클래스.
    매핑 정보는 Supabase의 category_mappings 테이블에서 가져옵니다.
    """

    def __init__(self, storage: SupabaseStorage):
        self.storage = storage
        self._mappings = {}
        self._load_mappings()

    def _load_mappings(self):
        """
        Supabase에서 모든 카테고리 매핑 정보를 로드하여 캐시합니다.
        """
        all_mappings = self.storage.get_all_category_mappings()
        for mapping in all_mappings:
            supplier_id = mapping.get('supplier_id')
            marketplace_id = mapping.get('marketplace_id')
            supplier_category_code = mapping.get('supplier_category_code')
            marketplace_category_code = mapping.get('marketplace_category_code')

            if supplier_id and marketplace_id and supplier_category_code and marketplace_category_code:
                key = (supplier_id, marketplace_id, supplier_category_code)
                self._mappings[key] = marketplace_category_code

    @lru_cache(maxsize=1024) # 자주 사용되는 매핑을 캐시
    def get_market_code(self, supplier_id: str, marketplace_id: str, supplier_category_code: str) -> Optional[str]:
        """
        주어진 공급사 카테고리 코드를 대상 마켓플레이스 카테고리 코드로 변환합니다.
        매핑 정보가 없으면 None을 반환합니다.
        """
        key = (supplier_id, marketplace_id, supplier_category_code)
        return self._mappings.get(key)

    def reload_mappings(self):
        """
        캐시된 매핑 정보를 다시 로드합니다 (매핑 변경 시 호출).
        """
        self._mappings = {}
        self._load_mappings()
        self.get_market_code.cache_clear() # lru_cache 초기화