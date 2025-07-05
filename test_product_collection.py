#!/usr/bin/env python3
"""
상품 수집 기능 테스트 스크립트
"""

import asyncio
import os
from datetime import datetime, timedelta
from dropshipping.suppliers.domeme.fetcher import DomemeFetcher
from dropshipping.suppliers.domeme.client import DomemeClient
from dropshipping.storage.supabase_storage import SupabaseStorage
from tests.fixtures.mock_storage import MockStorage
from dropshipping.monitoring import setup_logging, get_logger

# 로깅 설정
setup_logging(log_level="DEBUG")
logger = get_logger(__name__)

def test_domeme_client():
    """도매매 API 클라이언트 테스트"""
    print("\n=== 도매매 API 클라이언트 테스트 ===")
    
    try:
        # API 키 확인
        api_key = os.getenv("DOMEME_API_KEY")
        if not api_key:
            print("⚠️  DOMEME_API_KEY 환경 변수가 설정되지 않았습니다.")
            print("   Mock 모드로 진행합니다.")
            return False
            
        # 클라이언트 생성
        client = DomemeClient(api_key=api_key)
        print(f"✅ 도매매 클라이언트 생성 완료")
        
        # 상품 목록 조회 테스트
        print("\n상품 목록 조회 테스트...")
        result = client.search_products(start_row=1, end_row=5)
        
        print(f"✅ 조회 성공:")
        print(f"   - 총 상품 수: {result['total_count']}")
        print(f"   - 조회된 상품: {len(result['products'])}개")
        print(f"   - 다음 페이지 존재: {result['has_next']}")
        
        # 첫 번째 상품 상세 조회
        if result['products']:
            first_product = result['products'][0]
            product_no = first_product.get('productNo')
            print(f"\n상품 상세 조회 테스트 (상품번호: {product_no})...")
            
            detail = client.get_product_detail(product_no)
            print(f"✅ 상세 조회 성공:")
            print(f"   - 상품명: {detail.get('productName')}")
            print(f"   - 가격: {detail.get('price')}원")
            print(f"   - 재고: {detail.get('stockQuantity')}개")
            
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return False

def test_domeme_fetcher():
    """도매매 Fetcher 테스트"""
    print("\n=== 도매매 Fetcher 테스트 ===")
    
    try:
        # Mock 스토리지 사용
        storage = MockStorage()
        
        # Fetcher 생성
        api_key = os.getenv("DOMEME_API_KEY")
        fetcher = DomemeFetcher(storage=storage, api_key=api_key)
        print(f"✅ 도매매 Fetcher 생성 완료")
        
        # 상품 목록 조회
        print("\n상품 목록 조회 테스트...")
        products, has_next = fetcher.fetch_list(page=1)
        
        print(f"✅ 조회 성공:")
        print(f"   - 조회된 상품: {len(products)}개")
        print(f"   - 다음 페이지: {has_next}")
        
        if products:
            # 첫 번째 상품 출력
            first = products[0]
            print(f"\n첫 번째 상품 정보:")
            print(f"   - 상품번호: {first.get('productNo')}")
            print(f"   - 상품명: {first.get('productName')}")
            print(f"   - 가격: {first.get('price')}원")
            print(f"   - 재고: {first.get('stockQuantity')}개")
            
            # 변환 테스트
            print("\n변환 테스트...")
            standard_product = fetcher.transformer.to_standard(first)
            if standard_product:
                print(f"✅ 변환 성공:")
                print(f"   - ID: {standard_product.id}")
                print(f"   - 이름: {standard_product.name}")
                print(f"   - 가격: {standard_product.price}원")
                print(f"   - 이미지 수: {len(standard_product.images)}개")
            
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_incremental_sync():
    """증분 동기화 테스트"""
    print("\n=== 증분 동기화 테스트 ===")
    
    try:
        # Mock 스토리지 사용
        storage = MockStorage()
        
        # Fetcher 생성
        api_key = os.getenv("DOMEME_API_KEY")
        fetcher = DomemeFetcher(storage=storage, api_key=api_key)
        
        # 최근 7일간의 데이터만 수집
        since = datetime.now() - timedelta(days=7)
        print(f"✅ {since.strftime('%Y-%m-%d')} 이후 상품 수집 시작...")
        
        # 첫 번째 카테고리만 테스트 (최대 2페이지)
        fetcher.run_incremental(
            since=since,
            max_pages=2,
            category=fetcher.target_categories[0]
        )
        
        # 통계 출력
        stats = fetcher.stats
        print(f"\n✅ 동기화 완료:")
        print(f"   - 수집: {stats['fetched']}개")
        print(f"   - 저장: {stats['saved']}개")
        print(f"   - 중복: {stats['duplicates']}개")
        print(f"   - 오류: {stats['errors']}개")
        
        # 저장된 데이터 확인
        print(f"\n저장된 데이터 확인...")
        saved_products = storage.data.get("products_raw", {})
        print(f"✅ 총 {len(saved_products)}개 상품이 저장되었습니다.")
        
        if saved_products:
            # 첫 번째 저장된 상품 출력
            first_id = list(saved_products.keys())[0]
            first_product = saved_products[first_id]
            print(f"\n첫 번째 저장된 상품:")
            print(f"   - ID: {first_id}")
            print(f"   - 공급사 상품ID: {first_product['supplier_product_id']}")
            print(f"   - 수집 시간: {first_product['fetched_at']}")
            print(f"   - 상태: {first_product['status']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_full_pipeline():
    """전체 파이프라인 테스트"""
    print("\n=== 전체 수집 파이프라인 테스트 ===")
    
    try:
        # Mock 스토리지 사용
        storage = MockStorage()
        
        # Fetcher 생성
        api_key = os.getenv("DOMEME_API_KEY")
        fetcher = DomemeFetcher(storage=storage, api_key=api_key)
        
        print("전체 동기화 시작 (첫 번째 카테고리, 1페이지만)...")
        
        # 통계 초기화
        fetcher.reset_stats()
        
        # 첫 번째 카테고리의 1페이지만 수집
        category = fetcher.target_categories[0]
        products, has_next = fetcher.fetch_list(page=1, category=category)
        
        print(f"\n✅ {len(products)}개 상품 조회 완료")
        
        # 각 상품 처리
        success_count = 0
        for i, product in enumerate(products[:5]):  # 처음 5개만 테스트
            try:
                print(f"\n상품 {i+1} 처리 중...")
                
                # 원본 저장
                record_id = fetcher.save_raw(product)
                if record_id:
                    print(f"   ✅ 원본 데이터 저장: {record_id}")
                    
                    # 변환 및 처리
                    fetcher.process_product(record_id, product)
                    print(f"   ✅ 표준 형식으로 변환 완료")
                    
                    success_count += 1
                else:
                    print(f"   ⚠️  중복 데이터")
                    
            except Exception as e:
                print(f"   ❌ 처리 실패: {str(e)}")
        
        print(f"\n✅ 파이프라인 테스트 완료:")
        print(f"   - 성공: {success_count}개")
        print(f"   - 실패: {5 - success_count}개")
        
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """메인 테스트 실행"""
    print("=" * 60)
    print("드롭쉬핑 상품 수집 기능 점검")
    print("=" * 60)
    
    # 환경 변수 확인
    print("\n환경 변수 확인...")
    env_vars = {
        "DOMEME_API_KEY": os.getenv("DOMEME_API_KEY"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY")
    }
    
    for key, value in env_vars.items():
        if value:
            print(f"✅ {key}: 설정됨")
        else:
            print(f"⚠️  {key}: 미설정")
    
    # 테스트 실행
    tests = [
        ("API 클라이언트", test_domeme_client),
        ("Fetcher 기본 기능", test_domeme_fetcher),
        ("증분 동기화", test_incremental_sync),
        ("전체 파이프라인", test_full_pipeline)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"테스트: {test_name}")
        print('=' * 60)
        
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ 테스트 실행 중 오류: {str(e)}")
            results.append((test_name, False))
    
    # 최종 결과
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    
    for test_name, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{test_name}: {status}")
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print(f"\n전체: {success_count}/{total_count} 성공")
    
    if success_count == total_count:
        print("\n🎉 모든 테스트가 성공했습니다!")
    else:
        print("\n⚠️  일부 테스트가 실패했습니다.")

if __name__ == "__main__":
    main()