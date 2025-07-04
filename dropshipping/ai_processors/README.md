# AI 처리 모듈

이 모듈은 상품 정보 향상과 이미지 처리를 위한 AI 기능을 제공합니다.

## 주요 구성 요소

### 1. ModelRouter
AI 모델 선택과 비용 관리를 담당합니다.

**특징:**
- 작업 복잡도에 따른 자동 모델 선택
- 월간 예산 관리 및 사용량 추적
- 로컬(무료) 및 클라우드(유료) 모델 지원
- 예산 초과 시 무료 모델로 자동 전환

**지원 모델:**
- **로컬 (Ollama)**: Gemma 3B, DeepSeek-R1 7B, Qwen 3 14B
- **클라우드 (Gemini)**: Flash Mini, Flash

### 2. BaseAIProcessor
모든 AI 프로세서의 추상 기반 클래스입니다.

**제공 기능:**
- 재시도 로직 (tenacity)
- 배치 처리 지원
- 통계 추적
- 에러 핸들링

### 3. ProductEnhancer
상품 정보를 AI로 향상시킵니다.

**기능:**
- 상품명 최적화 (금지 키워드 제거, 핵심 키워드 추출)
- HTML 형식 상품 설명 자동 생성
- SEO 키워드 추출
- 가격대별 마케팅 키워드 생성

### 4. ImageProcessor
상품 이미지를 처리합니다.

**기능:**
- 이미지 캡션 생성 (Vision 모델 활용)
- 배경 제거 (향후 구현)
- 워터마크 추가
- 다양한 포맷 지원 (PNG, JPEG, WebP)
- 배치 처리
- 오래된 이미지 자동 정리

### 5. AIProcessingPipeline
모든 AI 프로세서를 통합한 파이프라인입니다.

**기능:**
- 상품 정보와 이미지 통합 처리
- 설정 기반 선택적 처리
- 배치 처리 (동시성 제어)
- 상세한 통계 및 비용 추적
- 처리 결과 자동 저장

## 사용 예제

### 기본 사용법

```python
from dropshipping.ai_processors.pipeline import AIProcessingPipeline
from dropshipping.storage.supabase_storage import SupabaseStorage

# 저장소 초기화
storage = SupabaseStorage(url="...", service_key="...")

# AI 파이프라인 초기화
pipeline = AIProcessingPipeline(
    storage=storage,
    config={
        "monthly_ai_budget": 50.0,
        "watermark_text": "MyStore.com",
        "enable_name_enhancement": True,
        "enable_description_generation": True,
        "enable_seo_keywords": True,
        "enable_image_processing": True
    }
)

# 단일 상품 처리
result = await pipeline.process_product(product)

# 배치 처리
results = await pipeline.process_batch(products, max_concurrent=5)
```

### 개별 프로세서 사용

```python
from dropshipping.ai_processors import ModelRouter, ProductEnhancer

# 모델 라우터 초기화
router = ModelRouter(monthly_budget=50.00)

# 상품 향상기 초기화
enhancer = ProductEnhancer(model_router=router)

# 상품명만 향상
result = await enhancer.process(product, enhance_type="name")

# 전체 향상 (이름, 설명, SEO)
result = await enhancer.process(product, enhance_type="all")
```

### 이미지 처리

```python
from dropshipping.ai_processors.image_processor import ImageProcessor

# 이미지 프로세서 초기화
processor = ImageProcessor(
    model_router=router,
    watermark_text="MyStore.com"
)

# 워터마크 추가
result = await processor.process(
    "path/to/image.jpg",
    process_type="watermark",
    output_format="jpg",
    quality=90
)

# 전체 처리 (캡션, 배경제거, 워터마크)
result = await processor.process(
    image,
    process_type="all"
)
```

## 설정 옵션

### ModelRouter 설정
- `monthly_budget`: 월간 AI 사용 예산 (기본: $50)

### ProductEnhancer 설정
- `banned_keywords`: 제거할 금지 키워드 목록
- `platform_keywords`: 플랫폼별 금지 키워드

### ImageProcessor 설정
- `watermark_text`: 워터마크 텍스트
- `watermark_opacity`: 워터마크 투명도 (0-255)
- `output_dir`: 처리된 이미지 저장 경로

### AIProcessingPipeline 설정
- `monthly_ai_budget`: 월간 예산
- `watermark_text`: 워터마크 텍스트
- `enable_name_enhancement`: 상품명 향상 활성화
- `enable_description_generation`: 설명 생성 활성화
- `enable_seo_keywords`: SEO 키워드 추출 활성화
- `enable_image_processing`: 이미지 처리 활성화

## 작업 유형 (TaskType)

- `NAME_ENHANCE`: 상품명 최적화
- `DESCRIPTION_GENERATE`: 상품 설명 생성
- `SEO_EXTRACT`: SEO 키워드 추출
- `IMAGE_CAPTION`: 이미지 캡션 생성
- `BACKGROUND_REMOVE`: 배경 제거

## 통계 및 모니터링

```python
# 파이프라인 통계
stats = pipeline.get_stats()
print(f"처리된 상품: {stats['products_processed']}")
print(f"성공률: {stats['success_rate']:.1%}")
print(f"AI 비용: ${stats['ai_usage']['current_usage']:.4f}")

# 모델별 사용량
usage = router.get_usage_report()
for model, count in usage['models_used'].items():
    print(f"{model}: {count}회")
```

## 테스트

```bash
# AI 프로세서 테스트 실행
pytest tests/test_ai_processors/ -v

# 커버리지 확인
pytest tests/test_ai_processors/ --cov=dropshipping.ai_processors
```

## 주의사항

1. **API 키 설정**: Gemini API를 사용하려면 환경 변수에 `GOOGLE_API_KEY` 설정 필요
2. **Ollama 설치**: 로컬 모델을 사용하려면 Ollama가 설치되어 있어야 함
3. **이미지 크기**: 대용량 이미지는 처리 시간이 오래 걸릴 수 있음
4. **비용 관리**: 클라우드 모델 사용 시 비용 발생, 예산 설정 권장

## 향후 개발 계획

1. 실제 AI 모델 통합 (현재는 시뮬레이션)
2. 배경 제거 API 통합 (remove.bg 등)
3. 이미지 최적화 기능 추가
4. 번역 기능 추가 (다국어 상품 설명)
5. A/B 테스트 지원