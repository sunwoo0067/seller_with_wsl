"""
상품 정보 향상 프로세서
상품명 최적화, 설명 생성, SEO 키워드 추출
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from dropshipping.ai_processors.base import AIProcessingError, BaseAIProcessor
from dropshipping.ai_processors.model_router import TaskConfig, TaskType
from dropshipping.models.product import StandardProduct


class ProductEnhancer(BaseAIProcessor):
    """상품 정보 향상 프로세서"""

    def __init__(self, model_router=None):
        """초기화"""
        # 기본 작업 설정
        default_config = TaskConfig(
            task_type=TaskType.PRODUCT_NAME_ENHANCE,
            complexity="medium",
            expected_tokens=300,
        )
        super().__init__(model_router, default_config)

        # 금지 키워드
        self.banned_keywords = {
            "최고",
            "최상",
            "최저가",
            "베스트",
            "1위",
            "인기",
            "핫딜",
            "특가",
            "세일",
            "할인",
            "무료배송",
            "당일배송",
            "빠른배송",
        }

    async def process(
        self,
        data: Union[StandardProduct, Dict[str, Any]],
        task_config: Optional[TaskConfig] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """상품 정보 향상 처리"""

        # 입력 검증
        if not self.validate_input(data):
            raise AIProcessingError("유효하지 않은 입력 데이터")

        # StandardProduct로 변환
        if isinstance(data, dict):
            product = StandardProduct(**data)
        else:
            product = data

        # 작업 설정
        config = task_config or self.default_task_config

        # 향상 유형 결정
        enhance_type = kwargs.get("enhance_type", "all")

        results = {}

        # 상품명 향상
        if enhance_type in ["all", "name"]:
            results["enhanced_name"] = await self._enhance_product_name(product, config)

        # 설명 생성
        if enhance_type in ["all", "description"]:
            results["generated_description"] = await self._generate_description(product, config)

        # SEO 키워드 추출
        if enhance_type in ["all", "seo"]:
            results["seo_keywords"] = await self._extract_seo_keywords(product, config)

        # 통계 업데이트
        self.stats["processed"] += 1

        return {
            "product_id": product.id,
            "original_name": product.name,
            "enhancements": results,
            "processed_at": datetime.now().isoformat(),
        }

    def validate_input(self, data: Any) -> bool:
        """입력 검증"""
        if isinstance(data, StandardProduct):
            return bool(data.name)
        elif isinstance(data, dict):
            return bool(data.get("name"))
        return False

    def prepare_prompt(self, data: Any, **kwargs) -> str:
        """프롬프트 준비"""
        # 구체적인 메서드에서 구현
        pass

    async def _enhance_product_name(self, product: StandardProduct, config: TaskConfig) -> str:
        """상품명 최적화"""

        # 작업 타입 설정
        config.task_type = TaskType.PRODUCT_NAME_ENHANCE

        # 모델 선택
        model = self.model_router.select_model(config)
        if not model:
            logger.error("상품명 향상용 모델을 찾을 수 없습니다")
            return product.name

        # 프롬프트 준비
        prompt = self._prepare_name_prompt(product)
        system_prompt = """당신은 전문 이커머스 상품명 최적화 전문가입니다.
주어진 상품명을 다음 기준에 따라 개선하세요:
1. 핵심 키워드를 앞쪽에 배치
2. 불필요한 특수문자와 중복 제거
3. 브랜드명은 유지
4. 60자 이내로 작성
5. 금지 키워드 사용 금지"""

        try:
            # 모델 실행
            result = await self._execute_with_model(model, prompt, system_prompt)

            # 결과 추출 및 정제
            enhanced_name = result["content"].strip()
            enhanced_name = self._clean_product_name(enhanced_name)

            # 검증
            if self._validate_enhanced_name(enhanced_name):
                logger.info(f"상품명 향상 완료: {product.name[:30]}... -> {enhanced_name[:30]}...")
                return enhanced_name
            else:
                logger.warning("향상된 상품명이 검증 실패")
                return product.name

        except Exception as e:
            logger.error(f"상품명 향상 실패: {str(e)}")
            return product.name

    def _prepare_name_prompt(self, product: StandardProduct) -> str:
        """상품명 프롬프트 준비"""
        return f"""다음 상품명을 개선해주세요:

원본 상품명: {product.name}
브랜드: {product.brand or "없음"}
카테고리: {product.category_name or "미분류"}

개선된 상품명만 출력하세요. 설명이나 추가 텍스트는 포함하지 마세요."""

    def _clean_product_name(self, name: str) -> str:
        """상품명 정제"""
        # 따옴표 제거
        name = name.strip("\"'")

        # 연속된 공백 제거
        name = re.sub(r"\s+", " ", name)

        # 특수문자 정리
        name = re.sub(r"[★☆♥♡]{2,}", "", name)
        name = re.sub(r"[!]{2,}", "!", name)
        name = re.sub(r"[~]{2,}", "~", name)

        # 대괄호 안 불필요한 내용 제거
        name = re.sub(r"\[(무료배송|당일발송|특가|신상품|인기상품)\]", "", name)

        return name.strip()

    def _validate_enhanced_name(self, name: str) -> bool:
        """향상된 상품명 검증"""
        # 길이 체크
        if len(name) < 10 or len(name) > 60:
            return False

        # 금지 키워드 체크
        for keyword in self.banned_keywords:
            if keyword in name:
                logger.warning(f"금지 키워드 발견: {keyword}")
                return False

        return True

    async def _generate_description(self, product: StandardProduct, config: TaskConfig) -> str:
        """상품 설명 생성"""

        # 작업 타입 설정
        config.task_type = TaskType.DESCRIPTION_GENERATE
        config.complexity = "high"
        config.expected_tokens = 800

        # 모델 선택
        model = self.model_router.select_model(config)
        if not model:
            logger.error("설명 생성용 모델을 찾을 수 없습니다")
            return ""

        # 프롬프트 준비
        prompt = self._prepare_description_prompt(product)
        system_prompt = """당신은 전문 상품 설명 작성자입니다.
매력적이고 신뢰할 수 있는 상품 설명을 작성하세요:
1. 주요 특징과 장점을 명확히 설명
2. 구매 욕구를 자극하는 감성적 표현 사용
3. 신뢰감을 주는 전문적인 톤 유지
4. HTML 태그를 사용한 구조화된 설명
5. 300-500자 분량"""

        try:
            # 모델 실행
            result = await self._execute_with_model(model, prompt, system_prompt)

            # 결과 추출
            description = result["content"].strip()

            # HTML 포맷팅
            if not description.startswith("<"):
                description = self._format_description_html(description)

            logger.info(f"상품 설명 생성 완료: {len(description)}자")
            return description

        except Exception as e:
            logger.error(f"설명 생성 실패: {str(e)}")
            return ""

    def _prepare_description_prompt(self, product: StandardProduct) -> str:
        """설명 프롬프트 준비"""

        # 옵션 정보 정리
        options_text = ""
        if product.options:
            options_list = []
            for opt in product.options:
                values = ", ".join(opt.values[:5])
                if len(opt.values) > 5:
                    values += f" 외 {len(opt.values) - 5}개"
                options_list.append(f"- {opt.name}: {values}")
            options_text = "\n".join(options_list)

        return f"""다음 상품에 대한 매력적인 설명을 작성해주세요:

상품명: {product.name}
브랜드: {product.brand or "없음"}
카테고리: {product.category_name or "미분류"}
가격: {product.price:,}원
원산지: {product.origin or "없음"}

{f"옵션:\n{options_text}" if options_text else ""}

{f"기존 설명:\n{product.description[:200]}..." if product.description else ""}

HTML 형식으로 구조화된 상품 설명을 작성하세요."""

    def _format_description_html(self, text: str) -> str:
        """텍스트를 HTML로 포맷팅"""
        lines = text.split("\n")
        formatted = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 목록 항목
            if line.startswith(("-", "•", "*")):
                if not formatted or not formatted[-1].startswith("<ul>"):
                    formatted.append("<ul>")
                formatted.append(f"<li>{line[1:].strip()}</li>")
                if len(lines) > lines.index(line) + 1:
                    next_line = lines[lines.index(line) + 1].strip()
                    if not next_line.startswith(("-", "•", "*")):
                        formatted.append("</ul>")
            # 제목 스타일 라인
            elif line.endswith(":"):
                formatted.append(f"<h4>{line}</h4>")
            # 일반 단락
            else:
                formatted.append(f"<p>{line}</p>")

        # 열린 ul 태그 닫기
        html = "\n".join(formatted)
        if "<ul>" in html and not html.endswith("</ul>"):
            html += "</ul>"

        return html

    async def _extract_seo_keywords(
        self, product: StandardProduct, config: TaskConfig
    ) -> List[str]:
        """SEO 키워드 추출"""

        # 작업 타입 설정
        config.task_type = TaskType.SEO_KEYWORDS
        config.complexity = "medium"
        config.expected_tokens = 200
        config.requires_json = True

        # 모델 선택
        model = self.model_router.select_model(config)
        if not model:
            logger.error("SEO 키워드 추출용 모델을 찾을 수 없습니다")
            return []

        # 프롬프트 준비
        prompt = self._prepare_seo_prompt(product)
        system_prompt = """당신은 SEO 전문가입니다.
상품과 관련된 검색 키워드를 추출하세요:
1. 구매 의도가 높은 키워드 우선
2. 롱테일 키워드 포함
3. 브랜드명 + 제품 유형 조합
4. 카테고리 관련 키워드
5. JSON 배열 형식으로 10-15개 출력"""

        try:
            # 모델 실행
            result = await self._execute_with_model(model, prompt, system_prompt)

            # JSON 파싱
            content = result["content"]
            if "```" in content:
                keywords = self.parse_json_response(content)
            else:
                # 간단한 파싱 시도
                keywords = [kw.strip().strip("\"'") for kw in content.split(",") if kw.strip()]

            # 배열이 아닌 경우 처리
            if isinstance(keywords, dict) and "keywords" in keywords:
                keywords = keywords["keywords"]

            # 정제
            keywords = [
                self._clean_keyword(kw) for kw in keywords if isinstance(kw, str) and len(kw) > 1
            ][:15]

            logger.info(f"SEO 키워드 {len(keywords)}개 추출")
            return keywords

        except Exception as e:
            logger.error(f"SEO 키워드 추출 실패: {str(e)}")
            # 기본 키워드 생성
            return self._generate_basic_keywords(product)

    def _prepare_seo_prompt(self, product: StandardProduct) -> str:
        """SEO 프롬프트 준비"""
        return f"""다음 상품의 SEO 키워드를 추출하세요:

상품명: {product.name}
브랜드: {product.brand or "없음"}
카테고리: {product.category_name or "미분류"}
가격대: {self._get_price_range(product.price)}

구매자가 검색할 만한 키워드를 JSON 배열 형식으로 출력하세요.
예: ["키워드1", "키워드2", ...]"""

    def _get_price_range(self, price: float) -> str:
        """가격대 문자열 반환"""
        if price < 10000:
            return "1만원 이하"
        elif price < 30000:
            return "1-3만원"
        elif price < 50000:
            return "3-5만원"
        elif price < 100000:
            return "5-10만원"
        elif price < 300000:
            return "10-30만원"
        else:
            return "30만원 이상"

    def _clean_keyword(self, keyword: str) -> str:
        """키워드 정제"""
        # 특수문자 제거
        keyword = re.sub(r"[^\w\s가-힣]", " ", keyword)
        # 연속 공백 제거
        keyword = re.sub(r"\s+", " ", keyword)
        return keyword.strip()

    def _generate_basic_keywords(self, product: StandardProduct) -> List[str]:
        """기본 키워드 생성 (폴백)"""
        keywords = []

        # 브랜드 + 카테고리
        if product.brand:
            keywords.append(product.brand)
            if product.category_name:
                keywords.append(f"{product.brand} {product.category_name}")

        # 상품명에서 주요 단어 추출
        name_parts = product.name.split()
        for part in name_parts:
            if len(part) > 2 and part not in self.banned_keywords:
                keywords.append(part)

        # 카테고리
        if product.category_name:
            keywords.append(product.category_name)

        # 가격대
        keywords.append(self._get_price_range(product.price))

        return list(dict.fromkeys(keywords))[:10]  # 중복 제거
