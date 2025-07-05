"""
카테고리 매핑 시스템
공급사별 카테고리를 표준 카테고리로 변환하고, 마켓플레이스별 카테고리로 매핑
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from loguru import logger


class CategoryLevel(Enum):
    """카테고리 레벨"""
    LEVEL_1 = 1  # 대분류
    LEVEL_2 = 2  # 중분류
    LEVEL_3 = 3  # 소분류
    LEVEL_4 = 4  # 세분류


@dataclass
class StandardCategory:
    """표준 카테고리 정의"""
    code: str
    name: str
    level: CategoryLevel
    parent_code: Optional[str] = None
    children: List[str] = None
    keywords: List[str] = None
    marketplace_mappings: Dict[str, str] = None  # 마켓플레이스별 카테고리 코드

    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.keywords is None:
            self.keywords = []
        if self.marketplace_mappings is None:
            self.marketplace_mappings = {}


@dataclass
class SupplierCategoryMapping:
    """공급사 카테고리 매핑"""
    supplier_id: str
    supplier_category_code: str
    supplier_category_name: str
    standard_category_code: str
    confidence: float = 1.0  # 매핑 신뢰도 (0.0 ~ 1.0)
    keywords: List[str] = None

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class CategoryMapper:
    """카테고리 매핑 관리자"""

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Args:
            data_dir: 카테고리 데이터 디렉터리 경로
        """
        self.data_dir = data_dir or Path(__file__).parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 표준 카테고리 체계
        self.standard_categories: Dict[str, StandardCategory] = {}
        
        # 공급사별 매핑
        self.supplier_mappings: Dict[str, Dict[str, SupplierCategoryMapping]] = {}
        
        # 키워드 기반 매핑 캐시
        self.keyword_cache: Dict[str, str] = {}
        
        # 초기 데이터 로드
        self._load_standard_categories()
        self._load_supplier_mappings()

    def _load_standard_categories(self):
        """표준 카테고리 체계 로드"""
        standard_file = self.data_dir / "standard_categories.json"
        
        if standard_file.exists():
            try:
                with open(standard_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        category = StandardCategory(**item)
                        self.standard_categories[category.code] = category
                logger.info(f"표준 카테고리 {len(self.standard_categories)}개 로드 완료")
                return
            except Exception as e:
                logger.error(f"표준 카테고리 로드 실패: {e}")
        
        # 기본 카테고리 체계 생성
        self._create_default_categories()
        self._save_standard_categories()

    def _create_default_categories(self):
        """기본 표준 카테고리 체계 생성"""
        # 대분류 (Level 1)
        level1_categories = [
            ("FASHION", "패션의류", ["의류", "패션", "옷", "의상", "블라우스", "셔츠", "바지", "스커트", "드레스", "코트", "자켓"]),
            ("BEAUTY", "뷰티", ["화장품", "미용", "스킨케어", "메이크업", "크림", "로션", "에센스", "마스크", "클렌징"]),
            ("ELECTRONICS", "전자제품", ["전자", "디지털", "가전", "IT", "스마트폰", "갤럭시", "아이폰", "노트북", "컴퓨터"]),
            ("HOME", "홈인테리어", ["가구", "인테리어", "홈데코", "생활용품", "침대", "소파", "테이블", "의자", "수납"]),
            ("SPORTS", "스포츠/레저", ["운동", "스포츠", "레저", "아웃도어", "운동화", "나이키", "아디다스", "헬스", "요가"]),
            ("FOOD", "식품", ["음식", "식료품", "건강식품", "간식", "차", "커피", "과자", "음료", "건강"]),
            ("BABY", "출산/육아", ["유아", "아기", "육아용품", "출산용품", "기저귀", "분유", "젖병", "유모차", "카시트"]),
            ("PET", "반려동물", ["펫", "동물", "강아지", "고양이", "사료", "간식", "용품", "장난감"]),
            ("BOOK", "도서", ["책", "서적", "교육", "학습", "소설", "만화", "참고서", "잡지"]),
            ("HOBBY", "취미/문구", ["취미", "문구", "DIY", "수집", "펜", "노트", "스티커", "만들기"]),
        ]

        for code, name, keywords in level1_categories:
            category = StandardCategory(
                code=code,
                name=name,
                level=CategoryLevel.LEVEL_1,
                keywords=keywords,
                marketplace_mappings={
                    "smartstore": self._get_smartstore_mapping(code),
                    "coupang": self._get_coupang_mapping(code),
                    "gmarket": self._get_gmarket_mapping(code),
                }
            )
            self.standard_categories[code] = category

        # 중분류 (Level 2) - 패션의류 예시
        fashion_level2 = [
            ("FASHION_WOMEN", "여성의류", "FASHION", ["여성", "레이디스", "우먼"]),
            ("FASHION_MEN", "남성의류", "FASHION", ["남성", "맨즈", "남자"]),
            ("FASHION_SHOES", "신발", "FASHION", ["신발", "슈즈", "구두", "운동화"]),
            ("FASHION_BAGS", "가방", "FASHION", ["가방", "백", "핸드백", "숄더백"]),
            ("FASHION_ACC", "액세서리", "FASHION", ["액세서리", "쥬얼리", "시계", "모자"]),
        ]

        for code, name, parent, keywords in fashion_level2:
            category = StandardCategory(
                code=code,
                name=name,
                level=CategoryLevel.LEVEL_2,
                parent_code=parent,
                keywords=keywords
            )
            self.standard_categories[code] = category
            # 부모 카테고리에 자식 추가
            if parent in self.standard_categories:
                self.standard_categories[parent].children.append(code)

        # 뷰티 중분류
        beauty_level2 = [
            ("BEAUTY_SKINCARE", "스킨케어", "BEAUTY", ["스킨케어", "기초화장품", "토너", "에센스"]),
            ("BEAUTY_MAKEUP", "메이크업", "BEAUTY", ["메이크업", "색조화장품", "립스틱", "파운데이션"]),
            ("BEAUTY_HAIR", "헤어케어", "BEAUTY", ["헤어", "샴푸", "린스", "헤어팩"]),
            ("BEAUTY_BODY", "바디케어", "BEAUTY", ["바디", "로션", "크림", "바디워시"]),
        ]

        for code, name, parent, keywords in beauty_level2:
            category = StandardCategory(
                code=code,
                name=name,
                level=CategoryLevel.LEVEL_2,
                parent_code=parent,
                keywords=keywords
            )
            self.standard_categories[code] = category
            if parent in self.standard_categories:
                self.standard_categories[parent].children.append(code)

    def _get_smartstore_mapping(self, standard_code: str) -> str:
        """스마트스토어 카테고리 매핑"""
        mappings = {
            "FASHION": "50000000",
            "BEAUTY": "50000001",
            "ELECTRONICS": "50000002",
            "HOME": "50000003",
            "SPORTS": "50000004",
            "FOOD": "50000005",
            "BABY": "50000006",
            "PET": "50000007",
            "BOOK": "50000008",
            "HOBBY": "50000009",
        }
        return mappings.get(standard_code, "50000000")

    def _get_coupang_mapping(self, standard_code: str) -> str:
        """쿠팡 카테고리 매핑"""
        mappings = {
            "FASHION": "11",
            "BEAUTY": "12",
            "ELECTRONICS": "13",
            "HOME": "14",
            "SPORTS": "15",
            "FOOD": "16",
            "BABY": "17",
            "PET": "18",
            "BOOK": "19",
            "HOBBY": "20",
        }
        return mappings.get(standard_code, "11")

    def _get_gmarket_mapping(self, standard_code: str) -> str:
        """G마켓 카테고리 매핑"""
        mappings = {
            "FASHION": "100000001",
            "BEAUTY": "100000002",
            "ELECTRONICS": "100000003",
            "HOME": "100000004",
            "SPORTS": "100000005",
            "FOOD": "100000006",
            "BABY": "100000007",
            "PET": "100000008",
            "BOOK": "100000009",
            "HOBBY": "100000010",
        }
        return mappings.get(standard_code, "100000001")

    def _load_supplier_mappings(self):
        """공급사별 매핑 로드"""
        suppliers = ["domeme", "ownerclan", "zentrade"]
        
        for supplier in suppliers:
            mapping_file = self.data_dir / f"{supplier}_mappings.json"
            if mapping_file.exists():
                try:
                    with open(mapping_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        mappings = {}
                        for item in data:
                            mapping = SupplierCategoryMapping(**item)
                            mappings[mapping.supplier_category_code] = mapping
                        self.supplier_mappings[supplier] = mappings
                    logger.info(f"{supplier} 매핑 {len(mappings)}개 로드 완료")
                except Exception as e:
                    logger.error(f"{supplier} 매핑 로드 실패: {e}")
            else:
                # 기본 매핑 생성
                self._create_default_supplier_mappings(supplier)

    def _create_default_supplier_mappings(self, supplier_id: str):
        """공급사별 기본 매핑 생성"""
        if supplier_id == "domeme":
            mappings = [
                SupplierCategoryMapping("domeme", "001", "패션의류", "FASHION", 1.0),
                SupplierCategoryMapping("domeme", "002", "패션잡화", "FASHION_ACC", 1.0),
                SupplierCategoryMapping("domeme", "003", "화장품/미용", "BEAUTY", 1.0),
                SupplierCategoryMapping("domeme", "004", "디지털/가전", "ELECTRONICS", 1.0),
                SupplierCategoryMapping("domeme", "005", "가구/인테리어", "HOME", 1.0),
                SupplierCategoryMapping("domeme", "006", "식품", "FOOD", 1.0),
                SupplierCategoryMapping("domeme", "007", "스포츠/레저", "SPORTS", 1.0),
                SupplierCategoryMapping("domeme", "008", "생활용품", "HOME", 0.8),
                SupplierCategoryMapping("domeme", "009", "출산/육아", "BABY", 1.0),
                SupplierCategoryMapping("domeme", "010", "반려동물", "PET", 1.0),
            ]
        elif supplier_id == "ownerclan":
            mappings = [
                SupplierCategoryMapping("ownerclan", "여성의류", "여성의류", "FASHION_WOMEN", 1.0),
                SupplierCategoryMapping("ownerclan", "남성의류", "남성의류", "FASHION_MEN", 1.0),
                SupplierCategoryMapping("ownerclan", "신발", "신발", "FASHION_SHOES", 1.0),
                SupplierCategoryMapping("ownerclan", "가방", "가방", "FASHION_BAGS", 1.0),
                SupplierCategoryMapping("ownerclan", "화장품", "화장품", "BEAUTY", 1.0),
                SupplierCategoryMapping("ownerclan", "디지털", "디지털", "ELECTRONICS", 1.0),
            ]
        elif supplier_id == "zentrade":
            mappings = [
                SupplierCategoryMapping("zentrade", "Fashion", "패션", "FASHION", 1.0),
                SupplierCategoryMapping("zentrade", "Beauty", "뷰티", "BEAUTY", 1.0),
                SupplierCategoryMapping("zentrade", "Electronics", "전자제품", "ELECTRONICS", 1.0),
                SupplierCategoryMapping("zentrade", "Home", "홈인테리어", "HOME", 1.0),
            ]
        else:
            mappings = []

        # 매핑 저장
        mapping_dict = {}
        for mapping in mappings:
            mapping_dict[mapping.supplier_category_code] = mapping
        
        self.supplier_mappings[supplier_id] = mapping_dict
        self._save_supplier_mappings(supplier_id)

    def map_supplier_category(
        self,
        supplier_id: str,
        supplier_category_code: str,
        supplier_category_name: str = None,
        product_name: str = None
    ) -> Tuple[Optional[str], float]:
        """
        공급사 카테고리를 표준 카테고리로 매핑

        Args:
            supplier_id: 공급사 ID
            supplier_category_code: 공급사 카테고리 코드
            supplier_category_name: 공급사 카테고리명 (옵션)
            product_name: 상품명 (키워드 매핑용, 옵션)

        Returns:
            Tuple[표준 카테고리 코드, 신뢰도]
        """
        # 1. 직접 매핑 확인
        if supplier_id in self.supplier_mappings:
            supplier_mappings = self.supplier_mappings[supplier_id]
            if supplier_category_code in supplier_mappings:
                mapping = supplier_mappings[supplier_category_code]
                return mapping.standard_category_code, mapping.confidence

        # 2. 카테고리명 기반 키워드 매핑
        if supplier_category_name:
            standard_code = self._map_by_keywords(supplier_category_name)
            if standard_code:
                confidence = 0.7  # 키워드 매핑은 낮은 신뢰도
                # 새로운 매핑 저장
                self._add_supplier_mapping(
                    supplier_id, supplier_category_code, supplier_category_name, 
                    standard_code, confidence
                )
                return standard_code, confidence

        # 3. 상품명 기반 키워드 매핑
        if product_name:
            standard_code = self._map_by_keywords(product_name)
            if standard_code:
                confidence = 0.5  # 상품명 기반은 더 낮은 신뢰도
                return standard_code, confidence

        # 4. 기본 카테고리 반환
        logger.warning(f"매핑되지 않은 카테고리: {supplier_id}.{supplier_category_code}")
        return "FASHION", 0.3  # 기본값

    def _map_by_keywords(self, text: str) -> Optional[str]:
        """키워드 기반 카테고리 매핑"""
        if not text:
            return None

        text_lower = text.lower()
        
        # 캐시 확인
        if text_lower in self.keyword_cache:
            return self.keyword_cache[text_lower]

        # 키워드 매칭
        best_match = None
        max_score = 0

        for category_code, category in self.standard_categories.items():
            score = 0
            for keyword in category.keywords:
                if keyword.lower() in text_lower:
                    score += len(keyword)  # 긴 키워드일수록 높은 점수

            if score > max_score:
                max_score = score
                best_match = category_code

        # 캐시 저장
        if best_match:
            self.keyword_cache[text_lower] = best_match

        return best_match

    def get_marketplace_category(
        self, 
        standard_category_code: str, 
        marketplace: str
    ) -> Optional[str]:
        """
        표준 카테고리를 마켓플레이스 카테고리로 변환

        Args:
            standard_category_code: 표준 카테고리 코드
            marketplace: 마켓플레이스 ID (smartstore, coupang, gmarket 등)

        Returns:
            마켓플레이스 카테고리 코드
        """
        if standard_category_code not in self.standard_categories:
            return None

        category = self.standard_categories[standard_category_code]
        return category.marketplace_mappings.get(marketplace)

    def get_category_hierarchy(self, category_code: str) -> List[StandardCategory]:
        """카테고리 계층 구조 반환"""
        hierarchy = []
        current_code = category_code

        while current_code and current_code in self.standard_categories:
            category = self.standard_categories[current_code]
            hierarchy.insert(0, category)  # 상위부터 정렬
            current_code = category.parent_code

        return hierarchy

    def _add_supplier_mapping(
        self,
        supplier_id: str,
        supplier_category_code: str,
        supplier_category_name: str,
        standard_category_code: str,
        confidence: float
    ):
        """새로운 공급사 매핑 추가"""
        if supplier_id not in self.supplier_mappings:
            self.supplier_mappings[supplier_id] = {}

        mapping = SupplierCategoryMapping(
            supplier_id=supplier_id,
            supplier_category_code=supplier_category_code,
            supplier_category_name=supplier_category_name,
            standard_category_code=standard_category_code,
            confidence=confidence
        )

        self.supplier_mappings[supplier_id][supplier_category_code] = mapping
        
        # 파일에 저장
        self._save_supplier_mappings(supplier_id)
        
        logger.info(f"새로운 매핑 추가: {supplier_id}.{supplier_category_code} -> {standard_category_code}")

    def _save_standard_categories(self):
        """표준 카테고리를 파일에 저장"""
        standard_file = self.data_dir / "standard_categories.json"
        try:
            data = []
            for category in self.standard_categories.values():
                data.append({
                    "code": category.code,
                    "name": category.name,
                    "level": category.level.value,
                    "parent_code": category.parent_code,
                    "children": category.children,
                    "keywords": category.keywords,
                    "marketplace_mappings": category.marketplace_mappings
                })
            
            with open(standard_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"표준 카테고리 저장 완료: {standard_file}")
        except Exception as e:
            logger.error(f"표준 카테고리 저장 실패: {e}")

    def _save_supplier_mappings(self, supplier_id: str):
        """공급사 매핑을 파일에 저장"""
        if supplier_id not in self.supplier_mappings:
            return

        mapping_file = self.data_dir / f"{supplier_id}_mappings.json"
        try:
            data = []
            for mapping in self.supplier_mappings[supplier_id].values():
                data.append({
                    "supplier_id": mapping.supplier_id,
                    "supplier_category_code": mapping.supplier_category_code,
                    "supplier_category_name": mapping.supplier_category_name,
                    "standard_category_code": mapping.standard_category_code,
                    "confidence": mapping.confidence,
                    "keywords": mapping.keywords
                })
            
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"{supplier_id} 매핑 저장 완료: {mapping_file}")
        except Exception as e:
            logger.error(f"{supplier_id} 매핑 저장 실패: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """매핑 통계 반환"""
        stats = {
            "standard_categories": len(self.standard_categories),
            "supplier_mappings": {},
            "keyword_cache_size": len(self.keyword_cache)
        }

        for supplier_id, mappings in self.supplier_mappings.items():
            stats["supplier_mappings"][supplier_id] = {
                "total": len(mappings),
                "high_confidence": len([m for m in mappings.values() if m.confidence >= 0.8]),
                "medium_confidence": len([m for m in mappings.values() if 0.5 <= m.confidence < 0.8]),
                "low_confidence": len([m for m in mappings.values() if m.confidence < 0.5])
            }

        return stats 