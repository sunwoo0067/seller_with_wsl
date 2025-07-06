import abc
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from dropshipping.storage.supabase_storage import SupabaseStorage

class BaseFetcher(abc.ABC):
    """
    모든 공급사 Fetcher의 추상 기본 클래스.
    공통 로직 (세션 관리, 해시 계산, raw 데이터 저장)을 정의합니다.
    """

    def __init__(self, storage: SupabaseStorage, supplier_name: str):
        self.storage = storage
        self.supplier_name = supplier_name

    @abc.abstractmethod
    def fetch_list(self, page: int) -> List[Dict]:
        """
        상품 목록을 페이지별로 가져옵니다.
        각 공급사 API에 맞게 구현해야 합니다.
        """
        pass

    @abc.abstractmethod
    def fetch_detail(self, item_id: str) -> Dict:
        """
        단일 상품의 상세 정보를 가져옵니다.
        각 공급사 API에 맞게 구현해야 합니다.
        """
        pass

    def _calculate_hash(self, data: Dict) -> str:
        """
        상품 데이터의 해시를 계산하여 중복 체크에 사용합니다.
        """
        # JSON 직렬화 시 키 순서를 정렬하여 일관된 해시 생성
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()

    def _save_raw(self, supplier_id: str, supplier_product_id: str, raw_json: Dict) -> bool:
        """
        원본 상품 데이터를 products_raw 테이블에 저장합니다.
        해시 충돌 시 (중복 상품) 저장을 건너뜁니다.
        """
        data_hash = self._calculate_hash(raw_json)
        try:
            self.storage.save_raw_product(
                raw_data={
                    "supplier_id": supplier_id,
                    "supplier_product_id": supplier_product_id,
                    "raw_json": raw_json,
                    "data_hash": data_hash
                }
            )
            print(f"Raw product saved: {supplier_product_id}")
            return True
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e):
                print(f"Duplicate raw product skipped: {supplier_product_id}")
                return False
            print(f"Error saving raw product {supplier_product_id}: {e}")
            # TODO: ingestion_logs에 에러 기록
            return False

    def run_incremental(self, supplier_id: str, since: Optional[datetime] = None):
        """
        증분 방식으로 상품을 수집하고 raw 테이블에 저장합니다.
        최신 상품부터 처리하며, 이미 처리된 상품은 건너뜁니다.
        """
        page = 1
        new_items_fetched = 0
        while True:
            print(f"Fetching list page {page} for supplier {supplier_id}...")
            items = self.fetch_list(page)
            if not items:
                print("No more items to fetch.")
                break

            for item in items:
                item_id = item.get('id') or item.get('product_id') # Assuming 'id' or 'product_id' is present
                if not item_id:
                    print(f"Warning: Item without ID found: {item}")
                    continue

                # TODO: since 파라미터 처리 로직 추가 (reg_date 비교 후 중단)
                # 현재는 모든 아이템 상세를 가져오는 것으로 가정

                detail_data = self.fetch_detail(item_id)
                if detail_data:
                    if self._save_raw(supplier_id, str(item_id), detail_data):
                        new_items_fetched += 1
                else:
                    print(f"Could not fetch detail for item {item_id}")
                    # TODO: ingestion_logs에 에러 기록

            page += 1
            # TODO: 실제 API 호출 시 페이지네이션 종료 조건 및 rate limit 고려

        print(f"Incremental run completed. New items fetched: {new_items_fetched}")