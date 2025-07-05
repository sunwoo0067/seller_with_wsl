"""
AI 프로세서 사용 예제
상품 정보 향상 데모
"""

import asyncio
from decimal import Decimal
from dropshipping.ai_processors import ModelRouter, ProductEnhancer, TaskConfig, TaskType
from dropshipping.models.product import StandardProduct, ProductOption, OptionType
from loguru import logger
import json


async def main():
    """메인 함수"""
    
    # 1. 모델 라우터 초기화 (월 $50 예산)
    router = ModelRouter(monthly_budget=Decimal("50.00"))
    logger.info("모델 라우터 초기화 완료")
    
    # 2. ProductEnhancer 초기화
    enhancer = ProductEnhancer(model_router=router)
    logger.info("상품 향상기 초기화 완료")
    
    # 3. 테스트 상품 생성
    product = StandardProduct(
        id="demo-001",
        supplier_id="domeme",
        supplier_product_id="DM2024001",
        name="[특가세일] 여성 니트 스웨터 가을 겨울 베이직 라운드넥 ★★★★★ 무료배송!!!",
        brand="StyleBasic",
        category_name="여성의류",
        price=Decimal("35900"),
        cost=Decimal("25000"),
        stock=150,
        origin="Korea",
        description="부드러운 소재의 베이직 니트 스웨터입니다.",
        options=[
            ProductOption(
                name="색상",
                type=OptionType.SELECT,
                values=["베이지", "블랙", "그레이", "네이비", "와인"]
            ),
            ProductOption(
                name="사이즈",
                type=OptionType.SELECT,
                values=["S (44-55)", "M (55-66)", "L (66-77)", "XL (77-88)"]
            )
        ]
    )
    
    logger.info(f"테스트 상품: {product.name}")
    
    # 4. 모델 선택 시연
    logger.info("\n=== 모델 선택 시연 ===")
    
    # 간단한 작업
    simple_task = TaskConfig(
        task_type=TaskType.PRODUCT_NAME_ENHANCE,
        complexity="low",
        expected_tokens=100
    )
    simple_model = router.select_model(simple_task)
    logger.info(f"간단한 작업 모델: {simple_model.model_name if simple_model else 'None'}")
    
    # 복잡한 작업
    complex_task = TaskConfig(
        task_type=TaskType.DESCRIPTION_GENERATE,
        complexity="high",
        expected_tokens=1000
    )
    complex_model = router.select_model(complex_task)
    logger.info(f"복잡한 작업 모델: {complex_model.model_name if complex_model else 'None'}")
    
    # 5. 상품명 향상 (실제 AI 호출 없이 시뮬레이션)
    logger.info("\n=== 상품 정보 향상 시뮬레이션 ===")
    
    # Mock 결과 (실제로는 AI가 생성)
    enhanced_results = {
        "product_id": product.id,
        "original_name": product.name,
        "enhancements": {
            "enhanced_name": "StyleBasic 여성 니트 스웨터 라운드넥 가을겨울 베이직",
            "generated_description": """
<h4>제품 특징:</h4>
<ul>
<li>부드럽고 따뜻한 프리미엄 니트 소재</li>
<li>베이직한 라운드넥 디자인으로 데일리룩 완성</li>
<li>5가지 세련된 컬러 선택 가능</li>
<li>편안한 핏감으로 체형 커버 효과</li>
</ul>

<h4>소재 및 관리:</h4>
<p>고급 아크릴 혼방 소재로 제작되어 보온성이 뛰어나며, 세탁 후에도 형태가 잘 유지됩니다.</p>

<h4>스타일링 팁:</h4>
<p>청바지나 슬랙스와 매치하여 캐주얼하게, 스커트와 함께 페미닌하게 연출 가능합니다.</p>
""",
            "seo_keywords": [
                "여성 니트",
                "StyleBasic 니트",
                "가을 니트 스웨터",
                "겨울 니트",
                "라운드넥 니트",
                "베이직 니트",
                "여성 스웨터",
                "3만원대 니트",
                "데일리 니트",
                "보온 니트"
            ]
        }
    }
    
    # 결과 출력
    logger.info(f"\n원본 상품명:\n{enhanced_results['original_name']}")
    logger.info(f"\n향상된 상품명:\n{enhanced_results['enhancements']['enhanced_name']}")
    logger.info(f"\n생성된 설명:\n{enhanced_results['enhancements']['generated_description'][:200]}...")
    logger.info(f"\nSEO 키워드:\n{', '.join(enhanced_results['enhancements']['seo_keywords'][:5])} ...")
    
    # 6. 사용량 리포트
    logger.info("\n=== 사용량 리포트 ===")
    
    # 가상의 사용량 기록
    router.record_usage("gemini-flash-mini", 500)   # 상품명
    router.record_usage("deepseek-r1-7b", 800)      # 설명 (무료)
    router.record_usage("gemini-flash-mini", 200)   # SEO
    
    report = router.get_usage_report()
    logger.info(f"월 예산: ${report['monthly_budget']:.2f}")
    logger.info(f"현재 사용량: ${report['current_usage']:.4f}")
    logger.info(f"남은 예산: ${report['remaining_budget']:.4f}")
    logger.info(f"사용률: {report['usage_percentage']:.1f}%")
    
    # 7. 배치 처리 예시
    logger.info("\n=== 배치 처리 예시 ===")
    
    # 여러 상품 준비
    products = [
        {"id": f"demo-{i:03d}", "name": f"테스트 상품 {i}", "price": 10000 * i, "cost": 7000 * i, "stock": 10}
        for i in range(1, 6)
    ]
    
    logger.info(f"{len(products)}개 상품 배치 처리 준비 완료")
    
    # 통계
    stats = enhancer.get_stats()
    logger.info(f"\n처리 통계:")
    logger.info(f"- 처리된 상품: {stats['processed']}")
    logger.info(f"- 실패: {stats['failed']}")
    logger.info(f"- 성공률: {stats['success_rate']:.1%}")


if __name__ == "__main__":
    # 로그 설정
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )
    
    # 실행
    asyncio.run(main())