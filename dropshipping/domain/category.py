"""
카테고리 매핑 모듈
공급사 카테고리를 마켓플레이스 카테고리로 변환
"""

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from dropshipping.storage.base import BaseStorage


@dataclass
class CategoryMapping:
    """카테고리 매핑 정보"""

    supplier_code: str
    supplier_name: str
    marketplace: str
    marketplace_code: str
    marketplace_name: str
    confidence: float = 1.0  # 매핑 신뢰도


class CategoryMapper:
    """카테고리 매핑 관리자"""

    def __init__(self, storage: Optional[BaseStorage] = None, mapping_file: Optional[str] = None):
        self.storage = storage
        self.mappings: Dict[str, Dict[str, List[CategoryMapping]]] = {}
        self.category_keywords: Dict[str, List[str]] = {}

        if self.storage:
            self.load_mappings_from_db()
        elif mapping_file and Path(mapping_file).exists():
            self.load_mappings(mapping_file)
        else:
            self._setup_default_mappings()

    def load_mappings_from_db(self):
        """DB에서 카테고리 매핑 정보 로드"""
        if not self.storage:
            logger.warning("Storage가 설정되지 않아 DB에서 매핑을 로드할 수 없습니다.")
            return

        # 모든 공급사와 마켓플레이스에 대한 매핑을 가져옴
        # 실제 구현에서는 필요한 만큼만 가져오도록 최적화 가능
        all_mappings = self.storage.get_all_category_mappings()  # 이 메서드는 storage에 추가 필요

        for mapping_data in all_mappings:
            mapping = CategoryMapping(
                supplier_code=mapping_data["supplier_category_code"],
                supplier_name=mapping_data["supplier_category_name"],
                marketplace=self._get_marketplace_code(
                    mapping_data["marketplace_id"]
                ),  # ID -> code 변환 필요
                marketplace_code=mapping_data["marketplace_category_code"],
                marketplace_name=mapping_data["marketplace_category_name"],
                confidence=float(mapping_data.get("confidence", 1.0)),
            )
            supplier_code = self._get_supplier_code(
                mapping_data["supplier_id"]
            )  # ID -> code 변환 필요
            self.add_mapping(mapping, supplier_id=supplier_code)

        logger.info(f"DB에서 {len(all_mappings)}개의 카테고리 매핑을 로드했습니다.")

    # ID-code 변환을 위한 헬퍼 메서드 (실제로는 storage나 별도 캐시에서 관리)
    def _get_marketplace_code(self, marketplace_id: str) -> str:
        # 임시 구현
        return "coupang"

    def _get_supplier_code(self, supplier_id: str) -> str:
        # 임시 구현
        return "domeme"

    def _setup_default_mappings(self):
        """기본 카테고리 매핑 설정"""
        # 도매매 -> 쿠팡 매핑 예시
        self.add_mapping(
            CategoryMapping(
                supplier_code="001001",
                supplier_name="패션의류/여성의류",
                marketplace="coupang",
                marketplace_code="194176",
                marketplace_name="여성패션",
            )
        )

        self.add_mapping(
            CategoryMapping(
                supplier_code="001002",
                supplier_name="패션의류/남성의류",
                marketplace="coupang",
                marketplace_code="194177",
                marketplace_name="남성패션",
            )
        )

        # 도매매 -> 11번가 매핑
        self.add_mapping(
            CategoryMapping(
                supplier_code="001001",
                supplier_name="패션의류/여성의류",
                marketplace="11st",
                marketplace_code="1001296",
                marketplace_name="여성의류",
            )
        )

        # 전자제품 카테고리
        self.add_mapping(
            CategoryMapping(
                supplier_code="002001",
                supplier_name="전자제품/스마트폰",
                marketplace="coupang",
                marketplace_code="194282",
                marketplace_name="휴대폰",
            )
        )

        # 키워드 기반 매핑을 위한 키워드 설정
        self.category_keywords = {
            "fashion_women": ["여성", "여자", "원피스", "블라우스", "스커트"],
            "fashion_men": ["남성", "남자", "셔츠", "바지", "정장"],
            "electronics": ["전자", "스마트폰", "노트북", "태블릿", "이어폰"],
            "beauty": ["화장품", "스킨케어", "메이크업", "뷰티", "코스메틱"],
            "food": ["식품", "과자", "음료", "건강식품", "다이어트"],
            "home": ["가구", "인테리어", "주방", "생활용품", "홈데코"],
            "sports": ["운동", "스포츠", "헬스", "요가", "아웃도어"],
            "kids": ["유아", "아동", "키즈", "장난감", "육아"],
        }

    def add_mapping(self, mapping: CategoryMapping, supplier_id: Optional[str] = None):
        """카테고리 매핑 추가"""
        supplier_id = "domeme"  # TODO: 공급사별로 구분 필요

        if supplier_id not in self.mappings:
            self.mappings[supplier_id] = {}

        if mapping.supplier_code not in self.mappings[supplier_id]:
            self.mappings[supplier_id][mapping.supplier_code] = []

        self.mappings[supplier_id][mapping.supplier_code].append(mapping)

        logger.debug(
            f"카테고리 매핑 추가: {mapping.supplier_name} -> "
            f"{mapping.marketplace}:{mapping.marketplace_name}"
        )

    def get_marketplace_category(
        self,
        supplier_id: str,
        supplier_category_code: str,
        supplier_category_name: str,
        marketplace: str,
    ) -> Optional[Tuple[str, str, float]]:
        """
        마켓플레이스 카테고리 조회

        Args:
            supplier_id: 공급사 ID
            supplier_category_code: 공급사 카테고리 코드
            supplier_category_name: 공급사 카테고리 이름
            marketplace: 마켓플레이스 (coupang, 11st, smartstore)

        Returns:
            Tuple[카테고리코드, 카테고리명, 신뢰도] or None
        """
        # 1. 정확한 매핑 찾기
        if supplier_id in self.mappings:
            if supplier_category_code in self.mappings[supplier_id]:
                for mapping in self.mappings[supplier_id][supplier_category_code]:
                    if mapping.marketplace == marketplace:
                        return (
                            mapping.marketplace_code,
                            mapping.marketplace_name,
                            mapping.confidence,
                        )

        # 2. 키워드 기반 매핑
        category_match = self._find_by_keywords(supplier_category_name, marketplace)
        if category_match:
            return category_match

        # 3. 유사도 기반 매핑
        similar_match = self._find_similar_category(
            supplier_id, supplier_category_name, marketplace
        )
        if similar_match:
            return similar_match

        logger.warning(
            f"카테고리 매핑 실패: {supplier_id}:{supplier_category_name} -> {marketplace}"
        )
        return None

    def _find_by_keywords(
        self, category_name: str, marketplace: str
    ) -> Optional[Tuple[str, str, float]]:
        """키워드 기반 카테고리 찾기"""
        category_name_lower = category_name.lower()

        # 각 카테고리 타입별로 매칭 점수 계산
        best_match = None
        best_score = 0

        for category_type, keywords in self.category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in category_name_lower)

            if score > best_score:
                best_score = score
                best_match = category_type

        # 매칭된 카테고리 타입에 따른 마켓플레이스 카테고리 반환
        if best_match and best_score > 0:
            return self._get_default_category(best_match, marketplace, confidence=0.7)

        return None

    def _find_similar_category(
        self, supplier_id: str, category_name: str, marketplace: str, threshold: float = 0.6
    ) -> Optional[Tuple[str, str, float]]:
        """유사도 기반 카테고리 찾기"""
        if supplier_id not in self.mappings:
            return None

        best_match = None
        best_similarity = 0

        # 모든 매핑된 카테고리와 비교
        for mappings in self.mappings[supplier_id].values():
            for mapping in mappings:
                if mapping.marketplace != marketplace:
                    continue

                # 문자열 유사도 계산
                similarity = SequenceMatcher(
                    None, category_name.lower(), mapping.supplier_name.lower()
                ).ratio()

                if similarity > best_similarity and similarity >= threshold:
                    best_similarity = similarity
                    best_match = mapping

        if best_match:
            return (
                best_match.marketplace_code,
                best_match.marketplace_name,
                best_similarity * best_match.confidence,
            )

        return None

    def _get_default_category(
        self, category_type: str, marketplace: str, confidence: float = 0.5
    ) -> Optional[Tuple[str, str, float]]:
        """카테고리 타입별 기본 마켓플레이스 카테고리"""
        defaults = {
            "coupang": {
                "fashion_women": ("194176", "여성패션", confidence),
                "fashion_men": ("194177", "남성패션", confidence),
                "electronics": ("194282", "전자제품", confidence),
                "beauty": ("194179", "뷰티", confidence),
                "food": ("194195", "식품", confidence),
                "home": ("194183", "생활/가구", confidence),
                "sports": ("194190", "스포츠/레저", confidence),
                "kids": ("194187", "유아동", confidence),
            },
            "11st": {
                "fashion_women": ("1001296", "여성의류", confidence),
                "fashion_men": ("1001295", "남성의류", confidence),
                "electronics": ("1001366", "디지털/가전", confidence),
                "beauty": ("1001286", "화장품/향수", confidence),
                "food": ("1001385", "식품", confidence),
                "home": ("1001323", "가구/인테리어", confidence),
                "sports": ("1001352", "스포츠/레저", confidence),
                "kids": ("1001300", "유아동", confidence),
            },
            "smartstore": {
                "fashion_women": ("50000000", "여성의류", confidence),
                "fashion_men": ("50000001", "남성의류", confidence),
                "electronics": ("50000003", "디지털/가전", confidence),
                "beauty": ("50000002", "화장품/미용", confidence),
                "food": ("50000006", "식품", confidence),
                "home": ("50000004", "생활/인테리어", confidence),
                "sports": ("50000005", "스포츠/레저", confidence),
                "kids": ("50000008", "출산/육아", confidence),
            },
        }

        if marketplace in defaults and category_type in defaults[marketplace]:
            return defaults[marketplace][category_type]

        return None

    def save_mappings(self, filepath: str):
        """매핑 정보 저장"""
        data = {"mappings": {}, "keywords": self.category_keywords}

        # CategoryMapping 객체를 dict로 변환
        for supplier_id, categories in self.mappings.items():
            data["mappings"][supplier_id] = {}
            for cat_code, mappings in categories.items():
                data["mappings"][supplier_id][cat_code] = [
                    {
                        "supplier_code": m.supplier_code,
                        "supplier_name": m.supplier_name,
                        "marketplace": m.marketplace,
                        "marketplace_code": m.marketplace_code,
                        "marketplace_name": m.marketplace_name,
                        "confidence": m.confidence,
                    }
                    for m in mappings
                ]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"카테고리 매핑 저장: {filepath}")

    def load_mappings(self, filepath: str):
        """매핑 정보 로드"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.mappings = {}
        self.category_keywords = data.get("keywords", {})

        # dict를 CategoryMapping 객체로 변환
        for supplier_id, categories in data.get("mappings", {}).items():
            self.mappings[supplier_id] = {}
            for cat_code, mappings in categories.items():
                self.mappings[supplier_id][cat_code] = [CategoryMapping(**m) for m in mappings]

        logger.info(f"카테고리 매핑 로드: {filepath}")

    def get_stats(self) -> Dict[str, Any]:
        """매핑 통계"""
        stats = {"total_mappings": 0, "by_supplier": {}, "by_marketplace": {}}

        for supplier_id, categories in self.mappings.items():
            supplier_count = 0

            for mappings in categories.values():
                for mapping in mappings:
                    stats["total_mappings"] += 1
                    supplier_count += 1

                    # 마켓플레이스별 통계
                    if mapping.marketplace not in stats["by_marketplace"]:
                        stats["by_marketplace"][mapping.marketplace] = 0
                    stats["by_marketplace"][mapping.marketplace] += 1

            stats["by_supplier"][supplier_id] = supplier_count

        return stats
