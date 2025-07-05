"""
JSON 파일 기반 저장소
개발/테스트용으로 DB 없이 로컬 파일에 데이터 저장
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from threading import Lock

from loguru import logger

from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage


class JSONStorage(BaseStorage):
    """JSON 파일 기반 저장소 구현"""

    def __init__(self, base_path: str = "./data"):
        """
        Args:
            base_path: 데이터 저장 경로
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # 데이터 파일 경로
        self.raw_file = self.base_path / "raw_products.json"
        self.processed_file = self.base_path / "processed_products.json"
        self.index_file = self.base_path / "index.json"

        # 메모리 캐시 및 락
        self._raw_data: Dict[str, Dict[str, Any]] = {}
        self._processed_data: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, Any] = {
            "hash_index": {},  # {hash: record_id}
            "supplier_index": {},  # {supplier_id: [record_ids]}
            "stats": {},
        }
        self._lock = Lock()

        # 파일에서 데이터 로드
        self._load_data()

    def _load_data(self):
        """파일에서 데이터 로드"""
        # Raw 데이터 로드
        if self.raw_file.exists():
            try:
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    self._raw_data = json.load(f)
                logger.info(f"Raw 데이터 {len(self._raw_data)}개 로드됨")
            except Exception as e:
                logger.error(f"Raw 데이터 로드 실패: {e}")
                self._raw_data = {}

        # Processed 데이터 로드
        if self.processed_file.exists():
            try:
                with open(self.processed_file, "r", encoding="utf-8") as f:
                    self._processed_data = json.load(f)
                logger.info(f"Processed 데이터 {len(self._processed_data)}개 로드됨")
            except Exception as e:
                logger.error(f"Processed 데이터 로드 실패: {e}")
                self._processed_data = {}

        # 인덱스 로드
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                logger.info("인덱스 로드됨")
            except Exception as e:
                logger.error(f"인덱스 로드 실패: {e}")
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _rebuild_index(self):
        """인덱스 재구성"""
        logger.info("인덱스 재구성 시작")

        self._index = {"hash_index": {}, "supplier_index": {}, "stats": {}}

        # Raw 데이터 인덱싱
        for record_id, data in self._raw_data.items():
            supplier_id = data.get("supplier_id")
            data_hash = data.get("data_hash")

            if data_hash:
                self._index["hash_index"][f"{supplier_id}:{data_hash}"] = record_id

            if supplier_id:
                if supplier_id not in self._index["supplier_index"]:
                    self._index["supplier_index"][supplier_id] = []
                self._index["supplier_index"][supplier_id].append(record_id)

        self._save_index()
        logger.info("인덱스 재구성 완료")

    def _save_data(self):
        """메모리 데이터를 파일에 저장"""
        try:
            # Raw 데이터 저장
            with open(self.raw_file, "w", encoding="utf-8") as f:
                json.dump(self._raw_data, f, ensure_ascii=False, indent=2, default=str)

            # Processed 데이터 저장
            with open(self.processed_file, "w", encoding="utf-8") as f:
                json.dump(self._processed_data, f, ensure_ascii=False, indent=2, default=str)

            # 인덱스 저장
            self._save_index()

        except Exception as e:
            logger.error(f"데이터 저장 실패: {e}")
            raise

    def _save_index(self):
        """인덱스 저장"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"인덱스 저장 실패: {e}")

    def save_raw_product(self, raw_data: Dict[str, Any]) -> str:
        """원본 상품 데이터 저장"""
        with self._lock:
            # ID 생성
            record_id = str(uuid.uuid4())

            # 타임스탬프 추가
            raw_data["id"] = record_id
            raw_data["created_at"] = datetime.now().isoformat()

            # 메모리에 저장
            self._raw_data[record_id] = raw_data

            # 인덱스 업데이트
            supplier_id = raw_data.get("supplier_id")
            data_hash = raw_data.get("data_hash")

            if data_hash:
                self._index["hash_index"][f"{supplier_id}:{data_hash}"] = record_id

            if supplier_id:
                if supplier_id not in self._index["supplier_index"]:
                    self._index["supplier_index"][supplier_id] = []
                self._index["supplier_index"][supplier_id].append(record_id)

            # 파일에 저장
            self._save_data()

            return record_id

    def save_processed_product(self, raw_id: str, product: StandardProduct) -> str:
        """처리된 상품 데이터 저장"""
        with self._lock:
            # StandardProduct을 dict로 변환
            product_dict = product.to_dict()
            product_dict["raw_id"] = raw_id
            product_dict["processed_at"] = datetime.now().isoformat()

            # 메모리에 저장
            self._processed_data[raw_id] = product_dict

            # Raw 데이터 상태 업데이트
            if raw_id in self._raw_data:
                self._raw_data[raw_id]["status"] = "processed"

            # 파일에 저장
            self._save_data()

            return raw_id

    def exists_by_hash(self, supplier_id: str, data_hash: str) -> bool:
        """해시로 중복 체크"""
        key = f"{supplier_id}:{data_hash}"
        return key in self._index["hash_index"]

    def get_raw_product(self, record_id: str) -> Optional[Dict[str, Any]]:
        """원본 상품 데이터 조회"""
        return self._raw_data.get(record_id)

    def get_processed_product(self, record_id: str) -> Optional[StandardProduct]:
        """처리된 상품 데이터 조회"""
        data = self._processed_data.get(record_id)
        if data:
            # dict를 StandardProduct로 변환
            return StandardProduct(**data)
        return None

    def list_raw_products(
        self,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """원본 상품 목록 조회"""
        results = []

        # 필터링할 레코드 ID 목록
        if supplier_id and supplier_id in self._index["supplier_index"]:
            record_ids = self._index["supplier_index"][supplier_id]
        else:
            record_ids = list(self._raw_data.keys())

        # 필터링 및 페이지네이션
        count = 0
        for record_id in record_ids:
            if count >= offset + limit:
                break

            data = self._raw_data.get(record_id)
            if not data:
                continue

            # 상태 필터
            if status and data.get("status") != status:
                continue

            if count >= offset:
                results.append(data)

            count += 1

        return results

    def update_status(self, record_id: str, status: str) -> bool:
        """상태 업데이트"""
        with self._lock:
            if record_id in self._raw_data:
                self._raw_data[record_id]["status"] = status
                self._raw_data[record_id]["updated_at"] = datetime.now().isoformat()
                self._save_data()
                return True
            return False

    def get_stats(self, supplier_id: Optional[str] = None) -> Dict[str, Any]:
        """통계 조회"""
        stats = {"total_raw": 0, "total_processed": 0, "by_status": {}, "by_supplier": {}}

        # Raw 데이터 통계
        for data in self._raw_data.values():
            sid = data.get("supplier_id")
            status = data.get("status", "unknown")

            if supplier_id and sid != supplier_id:
                continue

            stats["total_raw"] += 1

            # 상태별 통계
            if status not in stats["by_status"]:
                stats["by_status"][status] = 0
            stats["by_status"][status] += 1

            # 공급사별 통계
            if sid:
                if sid not in stats["by_supplier"]:
                    stats["by_supplier"][sid] = {"raw": 0, "processed": 0}
                stats["by_supplier"][sid]["raw"] += 1

        # Processed 데이터 통계
        for raw_id in self._processed_data:
            data = self._raw_data.get(raw_id, {})
            sid = data.get("supplier_id")

            if supplier_id and sid != supplier_id:
                continue

            stats["total_processed"] += 1

            if sid and sid in stats["by_supplier"]:
                stats["by_supplier"][sid]["processed"] += 1

        return stats

    def clear_all(self):
        """모든 데이터 삭제 (테스트용)"""
        with self._lock:
            self._raw_data.clear()
            self._processed_data.clear()
            self._index = {"hash_index": {}, "supplier_index": {}, "stats": {}}
            self._save_data()

    # BaseStorage 추상 메서드 구현
    async def upsert(self, table_name: str, records: List[Dict[str, Any]], on_conflict: str) -> List[Dict[str, Any]]:
        """레코드를 삽입하거나 업데이트합니다."""
        # JSONStorage는 upsert를 직접 지원하지 않으므로 NotImplementedError 발생
        raise NotImplementedError("JSONStorage does not support upsert operation directly.")

    def get_marketplace_upload(self, product_id: str, marketplace: str) -> Optional[Dict[str, Any]]:
        """마켓플레이스 업로드 기록을 조회합니다."""
        # JSONStorage는 마켓플레이스 업로드 기록을 별도로 저장하지 않으므로 NotImplementedError 발생
        raise NotImplementedError("JSONStorage does not store marketplace upload records.")

    def save_marketplace_upload(self, record: Dict[str, Any]):
        """마켓플레이스 업로드 기록을 저장합니다."""
        # JSONStorage는 마켓플레이스 업로드 기록을 별도로 저장하지 않으므로 NotImplementedError 발생
        raise NotImplementedError("JSONStorage does not store marketplace upload records.")

    def get_pricing_rules(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """가격 책정 규칙을 조회합니다."""
        pricing_rules_path = Path(__file__).parent.parent.parent / "demo_data" / "pricing" / "pricing_rules.json"
        if pricing_rules_path.exists():
            with open(pricing_rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
                if active_only:
                    return [rule for rule in rules if rule.get("is_active", True)]
                return rules
        return []

    def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        """모든 카테고리 매핑 정보를 조회합니다."""
        mappings = []
        categories_path = Path(__file__).parent.parent.parent / "demo_data" / "categories"
        for file_name in ["domeme_mappings.json", "ownerclan_mappings.json", "zentrade_mappings.json", "standard_categories.json"]:
            file_path = categories_path / file_name
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    mappings.extend(json.load(f))
        return mappings

    def get_supplier_code(self, supplier_id: str) -> str:
        """공급사 ID로 코드를 조회합니다."""
        # 간단한 매핑 또는 NotImplementedError
        if supplier_id == "domeme":
            return "DM"
        elif supplier_id == "ownerclan":
            return "OC"
        elif supplier_id == "zentrade":
            return "ZT"
        raise NotImplementedError(f"Supplier code for {supplier_id} not implemented in JSONStorage.")

    def get_marketplace_code(self, marketplace_id: str) -> str:
        """마켓플레이스 ID로 코드를 조회합니다."""
        # 간단한 매핑 또는 NotImplementedError
        if marketplace_id == "coupang":
            return "CP"
        elif marketplace_id == "elevenst":
            return "11ST"
        elif marketplace_id == "smartstore":
            return "SS"
        raise NotImplementedError(f"Marketplace code for {marketplace_id} not implemented in JSONStorage.")