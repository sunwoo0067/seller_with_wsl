#!/usr/bin/env python3
"""
🚀 드랍쉬핑 자동화 시스템 데모
실제 사용 시나리오를 보여주는 완전한 워크플로우
"""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any

# 프로젝트 루트 디렉터리를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dropshipping.suppliers.mock.mock_fetcher import MockFetcher
from dropshipping.transformers.domeme import DomemeTransformer
from dropshipping.transformers.category_mapper import CategoryMapper
from dropshipping.transformers.pricing_engine import PricingEngine, PricingStrategy
from dropshipping.models.product import StandardProduct

from loguru import logger


class DropshippingDemo:
    """드랍쉬핑 자동화 시스템 데모"""

    def __init__(self):
        """초기화"""
        self.demo_data_dir = project_root / "demo_data"
        self.demo_data_dir.mkdir(exist_ok=True)
        
        # 시스템 컴포넌트 초기화
        self.fetcher = MockFetcher()
        self.transformer = DomemeTransformer()
        self.category_mapper = CategoryMapper(data_dir=self.demo_data_dir / "categories")
        self.pricing_engine = PricingEngine(data_dir=self.demo_data_dir / "pricing")
        
        # 처리된 상품 목록
        self.processed_products: List[StandardProduct] = []
        
        # 통계 정보
        self.stats = {
            "total_fetched": 0,
            "successfully_processed": 0,
            "failed_processing": 0,
            "categories_mapped": set(),
            "average_margin": 0.0,
            "price_range": {"min": float('inf'), "max": 0}
        }

    def run_demo(self):
        """데모 실행"""
        logger.info("🎬 드랍쉬핑 자동화 시스템 데모 시작")
        logger.info("="*60)
        
        # 1. 시스템 소개
        self.show_system_overview()
        
        # 2. 공급사 데이터 수집
        self.demonstrate_data_fetching()
        
        # 3. 데이터 변환 및 처리
        self.demonstrate_data_processing()
        
        # 4. 카테고리 매핑
        self.demonstrate_category_mapping()
        
        # 5. 가격 책정
        self.demonstrate_pricing()
        
        # 6. 마켓플레이스별 최적화
        self.demonstrate_marketplace_optimization()
        
        # 7. 결과 분석
        self.show_results_analysis()
        
        # 8. 시스템 성능
        self.show_performance_metrics()
        
        logger.success("🎉 데모 완료!")

    def show_system_overview(self):
        """시스템 개요 소개"""
        logger.info("📋 시스템 개요")
        logger.info("-" * 30)
        
        overview = [
            "🔸 다중 공급사 지원 (도매매, 오너클랜, 젠트레이드)",
            "🔸 AI 기반 상품 정보 최적화",
            "🔸 자동 카테고리 매핑",
            "🔸 동적 가격 책정",
            "🔸 다중 마켓플레이스 업로드",
            "🔸 실시간 재고 동기화"
        ]
        
        for feature in overview:
            logger.info(feature)
            time.sleep(0.5)
        
        logger.info("")

    def demonstrate_data_fetching(self):
        """데이터 수집 시연"""
        logger.info("📥 1단계: 공급사 데이터 수집")
        logger.info("-" * 30)
        
        logger.info("🔍 도매매에서 상품 목록 조회 중...")
        
        # 첫 번째 페이지 조회
        products, has_next = self.fetcher.fetch_list(page=1)
        self.stats["total_fetched"] = len(products)
        
        logger.info(f"✅ {len(products)}개 상품 발견")
        logger.info(f"📄 다음 페이지 존재: {'예' if has_next else '아니오'}")
        
        # 샘플 상품 상세 정보 조회
        if products:
            sample_product = products[0]
            logger.info(f"🔍 샘플 상품 상세 정보 조회: {sample_product['productNo']}")
            
            detail = self.fetcher.fetch_detail(sample_product['productNo'])
            if detail:
                logger.info(f"  📦 상품명: {detail.get('productNm', 'N/A')}")
                logger.info(f"  💰 공급가: {detail.get('supplyPrice', 'N/A')}원")
                logger.info(f"  📊 재고: {detail.get('stockQty', 'N/A')}개")
        
        logger.info("")

    def demonstrate_data_processing(self):
        """데이터 처리 시연"""
        logger.info("🔄 2단계: 데이터 변환 및 표준화")
        logger.info("-" * 30)
        
        products, _ = self.fetcher.fetch_list(page=1)
        
        for i, raw_product in enumerate(products[:5]):  # 처음 5개 상품만 처리
            try:
                logger.info(f"🔄 상품 {i+1}/5 처리 중...")
                
                # 상세 정보 조회
                detail_data = self.fetcher.fetch_detail(raw_product["productNo"])
                if not detail_data:
                    continue
                
                # 표준 형식으로 변환
                standard_product = self.transformer.to_standard(detail_data)
                if standard_product:
                    self.processed_products.append(standard_product)
                    self.stats["successfully_processed"] += 1
                    
                    logger.info(f"  ✅ {standard_product.name[:30]}...")
                    logger.info(f"     원가: {standard_product.cost:,}원")
                    logger.info(f"     브랜드: {standard_product.brand or 'N/A'}")
                else:
                    self.stats["failed_processing"] += 1
                    logger.warning(f"  ❌ 변환 실패: {raw_product['productNo']}")
                
            except Exception as e:
                self.stats["failed_processing"] += 1
                logger.error(f"  ❌ 처리 오류: {str(e)}")
        
        success_rate = (self.stats["successfully_processed"] / len(products[:5])) * 100
        logger.info(f"📊 처리 성공률: {success_rate:.1f}%")
        logger.info("")

    def demonstrate_category_mapping(self):
        """카테고리 매핑 시연"""
        logger.info("🏷️ 3단계: 카테고리 매핑")
        logger.info("-" * 30)
        
        for product in self.processed_products:
            # 카테고리 매핑
            standard_code, confidence = self.category_mapper.map_supplier_category(
                "domeme",
                product.category_code or "unknown",
                product.category_name,
                product.name
            )
            
            # 표준 카테고리 적용
            old_category = product.category_code
            product.category_code = standard_code
            
            # 통계 업데이트
            self.stats["categories_mapped"].add(standard_code)
            
            logger.info(f"📋 {product.name[:25]}...")
            logger.info(f"   {old_category} → {standard_code} (신뢰도: {confidence:.1%})")
            
            # 마켓플레이스별 카테고리 매핑
            smartstore_cat = self.category_mapper.get_marketplace_category(standard_code, "smartstore")
            coupang_cat = self.category_mapper.get_marketplace_category(standard_code, "coupang")
            
            logger.info(f"   스마트스토어: {smartstore_cat}")
            logger.info(f"   쿠팡: {coupang_cat}")
            logger.info("")

    def demonstrate_pricing(self):
        """가격 책정 시연"""
        logger.info("💰 4단계: 동적 가격 책정")
        logger.info("-" * 30)
        
        total_margin = 0
        
        for product in self.processed_products:
            # 가격 계산
            pricing_result = self.pricing_engine.calculate_price(
                product.cost,
                supplier_id=product.supplier_id,
                category_code=product.category_code,
                product_name=product.name
            )
            
            # 가격 적용
            old_price = product.price
            product.price = pricing_result.final_price
            
            # 통계 업데이트
            total_margin += pricing_result.margin_rate
            self.stats["price_range"]["min"] = min(self.stats["price_range"]["min"], float(product.price))
            self.stats["price_range"]["max"] = max(self.stats["price_range"]["max"], float(product.price))
            
            logger.info(f"💰 {product.name[:25]}...")
            logger.info(f"   원가: {product.cost:,}원")
            logger.info(f"   판매가: {product.price:,}원 (마진: {pricing_result.margin_rate:.1%})")
            logger.info(f"   적용 규칙: {', '.join(pricing_result.applied_rules)}")
            logger.info(f"   전략: {pricing_result.strategy_used.value}")
            logger.info("")
        
        if self.processed_products:
            self.stats["average_margin"] = total_margin / len(self.processed_products)

    def demonstrate_marketplace_optimization(self):
        """마켓플레이스별 최적화 시연"""
        logger.info("🛒 5단계: 마켓플레이스별 최적화")
        logger.info("-" * 30)
        
        marketplaces = [
            {"name": "스마트스토어", "id": "smartstore", "commission": 0.025},
            {"name": "쿠팡", "id": "coupang", "commission": 0.08},
            {"name": "G마켓", "id": "gmarket", "commission": 0.06}
        ]
        
        sample_product = self.processed_products[0] if self.processed_products else None
        if not sample_product:
            logger.warning("최적화할 상품이 없습니다.")
            return
        
        logger.info(f"📦 샘플 상품: {sample_product.name}")
        logger.info(f"💰 기본 판매가: {sample_product.price:,}원")
        logger.info("")
        
        for marketplace in marketplaces:
            # 수수료 고려한 최적 가격 계산
            commission_rate = marketplace["commission"]
            commission_amount = sample_product.price * Decimal(str(commission_rate))
            net_revenue = sample_product.price - commission_amount
            profit = net_revenue - sample_product.cost
            profit_rate = float(profit / sample_product.cost) if sample_product.cost > 0 else 0
            
            # 카테고리 매핑
            marketplace_category = self.category_mapper.get_marketplace_category(
                sample_product.category_code, marketplace["id"]
            )
            
            logger.info(f"🏪 {marketplace['name']}")
            logger.info(f"   카테고리: {marketplace_category}")
            logger.info(f"   수수료: {commission_rate:.1%} ({commission_amount:,.0f}원)")
            logger.info(f"   순수익: {net_revenue:,}원")
            logger.info(f"   실제 마진: {profit_rate:.1%}")
            
            # 수익성 평가
            if profit_rate >= 0.15:
                logger.success(f"   ✅ 추천: 높은 수익성")
            elif profit_rate >= 0.05:
                logger.info(f"   ⚠️ 보통: 적정 수익성")
            else:
                logger.warning(f"   ❌ 비추천: 낮은 수익성")
            
            logger.info("")

    def show_results_analysis(self):
        """결과 분석"""
        logger.info("📊 6단계: 결과 분석")
        logger.info("-" * 30)
        
        logger.info(f"📈 처리 통계:")
        logger.info(f"   총 수집 상품: {self.stats['total_fetched']}개")
        logger.info(f"   성공 처리: {self.stats['successfully_processed']}개")
        logger.info(f"   실패 처리: {self.stats['failed_processing']}개")
        logger.info(f"   성공률: {(self.stats['successfully_processed'] / max(self.stats['total_fetched'], 1)) * 100:.1f}%")
        logger.info("")
        
        logger.info(f"🏷️ 카테고리 분석:")
        logger.info(f"   매핑된 카테고리 수: {len(self.stats['categories_mapped'])}개")
        for category in sorted(self.stats['categories_mapped']):
            count = sum(1 for p in self.processed_products if p.category_code == category)
            logger.info(f"   {category}: {count}개 상품")
        logger.info("")
        
        logger.info(f"💰 가격 분석:")
        if self.stats['price_range']['min'] != float('inf'):
            logger.info(f"   평균 마진율: {self.stats['average_margin']:.1%}")
            logger.info(f"   가격 범위: {self.stats['price_range']['min']:,.0f}원 ~ {self.stats['price_range']['max']:,.0f}원")
        
        # 수익성 분석
        high_margin_products = [p for p in self.processed_products 
                              if (p.price - p.cost) / p.cost > 0.3]
        logger.info(f"   고마진 상품 (30% 이상): {len(high_margin_products)}개")
        logger.info("")

    def show_performance_metrics(self):
        """성능 지표"""
        logger.info("⚡ 7단계: 시스템 성능")
        logger.info("-" * 30)
        
        # 카테고리 매퍼 통계
        category_stats = self.category_mapper.get_statistics()
        logger.info(f"🏷️ 카테고리 매핑 엔진:")
        logger.info(f"   표준 카테고리: {category_stats['standard_categories']}개")
        logger.info(f"   공급사 매핑: {sum(v['total'] for v in category_stats['supplier_mappings'].values())}개")
        logger.info(f"   캐시 크기: {category_stats['keyword_cache_size']}개")
        logger.info("")
        
        # 가격 엔진 통계
        pricing_stats = self.pricing_engine.get_statistics()
        logger.info(f"💰 가격 책정 엔진:")
        logger.info(f"   활성 규칙: {pricing_stats['active_rules']}개")
        logger.info(f"   계산 히스토리: {pricing_stats['calculation_history_size']}건")
        logger.info(f"   평균 마진율: {pricing_stats['average_margin']:.1%}")
        
        strategy_dist = pricing_stats['strategy_distribution']
        logger.info(f"   전략 분포:")
        for strategy, count in strategy_dist.items():
            logger.info(f"     {strategy}: {count}개 규칙")
        logger.info("")
        
        # 전체 시스템 효율성
        if self.processed_products:
            avg_processing_time = 0.5  # 예상 처리 시간 (초)
            total_time = len(self.processed_products) * avg_processing_time
            
            logger.info(f"⚡ 처리 성능:")
            logger.info(f"   상품당 평균 처리 시간: {avg_processing_time}초")
            logger.info(f"   총 처리 시간: {total_time:.1f}초")
            logger.info(f"   시간당 처리량: {3600 / avg_processing_time:.0f}개 상품")

    def show_sample_product_details(self):
        """샘플 상품 상세 정보"""
        if not self.processed_products:
            return
        
        logger.info("📦 샘플 상품 상세 정보")
        logger.info("-" * 30)
        
        product = self.processed_products[0]
        
        logger.info(f"🏷️ 기본 정보:")
        logger.info(f"   ID: {product.id}")
        logger.info(f"   상품명: {product.name}")
        logger.info(f"   브랜드: {product.brand or 'N/A'}")
        logger.info(f"   제조사: {product.manufacturer or 'N/A'}")
        logger.info(f"   원산지: {product.origin or 'N/A'}")
        logger.info("")
        
        logger.info(f"💰 가격 정보:")
        logger.info(f"   원가: {product.cost:,}원")
        logger.info(f"   판매가: {product.price:,}원")
        logger.info(f"   정가: {product.list_price:,}원")
        margin_rate = float((product.price - product.cost) / product.cost) if product.cost > 0 else 0
        logger.info(f"   마진율: {margin_rate:.1%}")
        logger.info("")
        
        logger.info(f"📊 재고 및 상태:")
        logger.info(f"   재고: {product.stock}개")
        logger.info(f"   상태: {product.status.value}")
        logger.info("")
        
        logger.info(f"🏷️ 카테고리:")
        logger.info(f"   코드: {product.category_code}")
        logger.info(f"   이름: {product.category_name}")
        if product.category_path:
            logger.info(f"   경로: {' > '.join(product.category_path)}")
        logger.info("")
        
        if product.images:
            logger.info(f"🖼️ 이미지: {len(product.images)}개")
        
        if product.options:
            logger.info(f"⚙️ 옵션: {len(product.options)}개")
            for option in product.options:
                logger.info(f"   {option.name}: {', '.join(option.values)}")


def main():
    """메인 함수"""
    # 환경 변수 설정
    os.environ.setdefault("ENV", "demo")
    os.environ.setdefault("CACHE_TTL", "3600")
    
    # 로그 설정
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True
    )
    
    # 데모 실행
    demo = DropshippingDemo()
    demo.run_demo()
    
    # 상세 정보 표시 (옵션)
    if "--detailed" in sys.argv:
        demo.show_sample_product_details()


if __name__ == "__main__":
    main() 