"""
AI 처리 파이프라인 사용 예제
이미지 처리를 포함한 완전한 AI 파이프라인 데모
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from datetime import datetime

from dropshipping.ai_processors import ModelRouter, TaskConfig, TaskType
from dropshipping.ai_processors.pipeline import AIProcessingPipeline
from dropshipping.storage.json_storage import JSONStorage
from dropshipping.models.product import StandardProduct, ProductImage


async def main():
    print("=== AI 처리 파이프라인 예제 ===\n")
    
    # 1. 저장소 초기화 (실제로는 SupabaseStorage 사용)
    storage = JSONStorage(base_path="./data")
    
    # 2. AI 파이프라인 초기화
    pipeline = AIProcessingPipeline(
        storage=storage,
        config={
            "monthly_ai_budget": 50.0,  # 월 $50 예산
            "watermark_text": "MyStore.com",
            "enable_name_enhancement": True,
            "enable_description_generation": True,
            "enable_seo_keywords": True,
            "enable_image_processing": True
        }
    )
    
    print("✅ AI 파이프라인 초기화 완료")
    print(f"- 월 예산: $50.00")
    print(f"- 워터마크: MyStore.com")
    print(f"- 활성화된 기능: 상품명/설명/SEO/이미지\n")
    
    # 3. 테스트 상품 생성
    products = [
        StandardProduct(
            id="ai-test-001",
            supplier_id="domeme",
            supplier_product_id="DM001",
            name="[도매매] 최신형 블루투스 이어폰 TWS 무선충전 방수",
            description="고품질 블루투스 이어폰입니다.",
            price=29900,
            cost=15000,
            category="전자기기/이어폰",
            images=[
                ProductImage(
                    url="https://example.com/earphone1.jpg",
                    is_main=True
                ),
                ProductImage(
                    url="https://example.com/earphone2.jpg",
                    is_main=False
                )
            ],
            stock_quantity=100,
            tags=["블루투스", "이어폰"]
        ),
        StandardProduct(
            id="ai-test-002",
            supplier_id="domeme",
            supplier_product_id="DM002",
            name="[특가] 여성 캐주얼 롱원피스 봄가을 데일리룩",
            description="편안한 착용감의 원피스",
            price=19900,
            cost=8000,
            category="의류/원피스",
            images=[
                ProductImage(
                    url="https://example.com/dress1.jpg",
                    is_main=True
                )
            ],
            stock_quantity=50,
            tags=["원피스", "여성의류"]
        ),
        StandardProduct(
            id="ai-test-003",
            supplier_id="domeme",
            supplier_product_id="DM003",
            name="강아지 자동급식기 스마트 타이머 대용량",
            description="반려동물 자동 급식기",
            price=45000,
            cost=25000,
            category="애완용품/급식기",
            images=[],  # 이미지 없는 상품
            stock_quantity=30
        )
    ]
    
    print(f"📦 처리할 상품 {len(products)}개 준비 완료\n")
    
    # 4. 개별 상품 처리 예제
    print("=== 개별 상품 처리 ===")
    
    result = await pipeline.process_product(
        products[0],
        options={
            "enhance_name": True,
            "generate_description": True,
            "extract_seo": True,
            "save_to_storage": False  # 예제에서는 저장 생략
        }
    )
    
    print(f"\n✅ 상품 처리 완료: {result['product_id']}")
    print(f"- 처리 시간: {result['processing_time']:.2f}초")
    print(f"- AI 비용: ${result['ai_cost']:.4f}")
    
    if result['enhancements']:
        print("\n📝 향상된 정보:")
        if 'enhanced_name' in result['enhancements']:
            print(f"  - 상품명: {result['enhancements']['enhanced_name']}")
        if 'generated_description' in result['enhancements']:
            desc = result['enhancements']['generated_description'][:100] + "..."
            print(f"  - 설명: {desc}")
        if 'seo_keywords' in result['enhancements']:
            print(f"  - SEO 키워드: {', '.join(result['enhancements']['seo_keywords'][:5])}")
    
    if result['processed_images']:
        print(f"\n🖼️  처리된 이미지: {len(result['processed_images'])}개")
    
    if result['errors']:
        print(f"\n❌ 오류: {result['errors']}")
    
    # 5. 배치 처리 예제
    print("\n\n=== 배치 처리 ===")
    
    batch_results = await pipeline.process_batch(
        products,
        options={
            "save_to_storage": False,
            "skip_background_removal": True  # 배경 제거 생략 (빠른 처리)
        },
        max_concurrent=2
    )
    
    print(f"\n✅ 배치 처리 완료")
    print(f"- 성공: {len(batch_results)}개")
    print(f"- 실패: {len(products) - len(batch_results)}개")
    
    # 6. 통계 확인
    print("\n\n=== 처리 통계 ===")
    
    stats = pipeline.get_stats()
    
    print(f"📊 전체 통계:")
    print(f"- 처리된 상품: {stats['products_processed']}개")
    print(f"- 실패한 상품: {stats['products_failed']}개")
    print(f"- 성공률: {stats['success_rate']*100:.1f}%")
    print(f"- AI 향상 수: {stats['ai_enhancements']}개")
    print(f"- 처리된 이미지: {stats['images_processed']}개")
    
    print(f"\n💰 AI 사용량:")
    ai_usage = stats['ai_usage']
    print(f"- 현재 사용량: ${ai_usage['current_usage']:.4f}")
    print(f"- 월 예산: ${ai_usage['monthly_budget']:.2f}")
    print(f"- 잔여 예산: ${ai_usage['monthly_budget'] - ai_usage['current_usage']:.4f}")
    
    # 7. 모델별 사용량 확인
    if ai_usage.get('models_used'):
        print(f"\n🤖 모델별 사용:")
        for model, count in ai_usage['models_used'].items():
            print(f"  - {model}: {count}회")
    
    # 8. 프로세서별 통계
    print(f"\n📈 프로세서별 통계:")
    
    enhancer_stats = stats.get('enhancer_stats', {})
    if enhancer_stats:
        print(f"  ProductEnhancer:")
        print(f"    - 처리: {enhancer_stats.get('processed', 0)}개")
        print(f"    - 실패: {enhancer_stats.get('failed', 0)}개")
    
    image_stats = stats.get('image_processor_stats', {})
    if image_stats:
        print(f"  ImageProcessor:")
        print(f"    - 처리: {image_stats.get('processed', 0)}개")
        print(f"    - 실패: {image_stats.get('failed', 0)}개")
    
    # 9. 파이프라인 로그
    pipeline.log_pipeline_run(
        status="completed",
        details={
            "example": "ai_pipeline_demo",
            "products_count": len(products)
        }
    )
    
    print("\n✅ AI 파이프라인 예제 완료!")


if __name__ == "__main__":
    asyncio.run(main())