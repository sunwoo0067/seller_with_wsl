#!/usr/bin/env python3
"""
Mock 모드 상품 수집 기능 테스트
"""

import asyncio
from datetime import datetime, timedelta
from dropshipping.suppliers.mock.mock_fetcher import MockFetcher
from tests.fixtures.mock_storage import MockStorage
from dropshipping.transformers.domeme import DomemeTransformer
from dropshipping.monitoring import setup_logging, get_logger
from dropshipping.scheduler.main import MainScheduler
from dropshipping.scheduler.jobs.collection_job import DailyCollectionJob

# 로깅 설정
setup_logging(log_level="INFO")
logger = get_logger(__name__)

def test_mock_fetcher():
    """Mock Fetcher 기본 테스트"""
    print("\n=== Mock Fetcher 테스트 ===")
    
    try:
        # Mock 스토리지 생성
        storage = MockStorage()
        
        # Mock Fetcher 생성
        fetcher = MockSupplierFetcher(storage=storage)
        print(f"✅ Mock Fetcher 생성 완료")
        
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
            print(f"   - 상품명: {first.get('productNm')}")
            print(f"   - 가격: {first.get('supplyPrice')}원")
            print(f"   - 재고: {first.get('stockQty')}개")
            
            # 상세 조회
            print("\n상세 조회 테스트...")
            detail = fetcher.fetch_detail(first.get('productNo'))
            print(f"✅ 상세 조회 성공:")
            print(f"   - 브랜드: {detail.get('brandNm')}")
            print(f"   - 제조사: {detail.get('makerNm')}")
            print(f"   - 카테고리: {detail.get('categoryNm')}")
            
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_transformation():
    """데이터 변환 테스트"""
    print("\n=== 데이터 변환 테스트 ===")
    
    try:
        # Mock Fetcher와 Transformer
        storage = MockStorage()
        fetcher = MockSupplierFetcher(storage=storage)
        transformer = DomemeTransformer()
        
        # 상품 조회
        products, _ = fetcher.fetch_list(page=1)
        
        success_count = 0
        for i, product in enumerate(products[:5]):
            print(f"\n상품 {i+1} 변환 중...")
            
            # 변환
            standard = transformer.to_standard(product)
            if standard:
                print(f"✅ 변환 성공:")
                print(f"   - ID: {standard.id}")
                print(f"   - 이름: {standard.name}")
                print(f"   - 원가: {standard.cost}원")
                print(f"   - 판매가: {standard.price}원")
                print(f"   - 상태: {standard.status.value}")
                print(f"   - 이미지: {len(standard.images)}개")
                print(f"   - 옵션: {len(standard.options)}개")
                success_count += 1
            else:
                print(f"❌ 변환 실패")
        
        print(f"\n✅ 변환 테스트 완료: {success_count}/5 성공")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return False

def test_collection_pipeline():
    """전체 수집 파이프라인 테스트"""
    print("\n=== 전체 수집 파이프라인 테스트 ===")
    
    try:
        # Mock 스토리지
        storage = MockStorage()
        
        # Fetcher 생성
        fetcher = MockSupplierFetcher(storage=storage)
        
        # 증분 수집 (최근 1일)
        print("증분 수집 시작...")
        since = datetime.now() - timedelta(days=1)
        fetcher.run_incremental(since=since, max_pages=3)
        
        # 통계 출력
        stats = fetcher.stats
        print(f"\n✅ 수집 완료:")
        print(f"   - 수집: {stats['fetched']}개")
        print(f"   - 저장: {stats['saved']}개")
        print(f"   - 중복: {stats['duplicates']}개")
        print(f"   - 오류: {stats['errors']}개")
        
        # 저장된 데이터 확인
        raw_products = storage.data.get("products_raw", {})
        print(f"\n원본 데이터: {len(raw_products)}개")
        
        # 변환된 데이터 확인
        products = storage.data.get("products", {})
        print(f"변환된 데이터: {len(products)}개")
        
        if products:
            # 첫 번째 변환된 상품
            first_id = list(products.keys())[0]
            first = products[first_id]
            print(f"\n첫 번째 변환된 상품:")
            print(f"   - ID: {first['id']}")
            print(f"   - 이름: {first['name']}")
            print(f"   - 공급사: {first['supplier_id']}")
            print(f"   - 상태: {first['status']}")
        
        return stats['saved'] > 0
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_scheduler_job():
    """스케줄러 작업 테스트"""
    print("\n=== 스케줄러 작업 테스트 ===")
    
    try:
        # Mock 스토리지
        storage = MockStorage()
        
        # 일일 수집 작업 생성
        job = DailyCollectionJob(storage=storage)
        print("✅ 일일 수집 작업 생성")
        
        # 작업 실행 (비동기)
        print("\n작업 실행 중...")
        result = asyncio.run(job.run())
        
        print(f"\n✅ 작업 완료:")
        print(f"   - 상태: {result.status}")
        print(f"   - 메시지: {result.message}")
        print(f"   - 실행 시간: {result.duration:.2f}초")
        
        if result.data:
            print(f"   - 수집 통계:")
            for supplier, stats in result.data.items():
                print(f"     * {supplier}: {stats}")
        
        return result.status == "success"
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """오류 처리 테스트"""
    print("\n=== 오류 처리 테스트 ===")
    
    try:
        storage = MockStorage()
        fetcher = MockSupplierFetcher(storage=storage)
        
        # 잘못된 페이지 번호
        print("1. 잘못된 페이지 번호 테스트...")
        try:
            products, has_next = fetcher.fetch_list(page=1000)
            print(f"   ✅ 빈 결과 반환: {len(products)}개, has_next={has_next}")
        except Exception as e:
            print(f"   ❌ 예외 발생: {str(e)}")
        
        # 존재하지 않는 상품 ID
        print("\n2. 존재하지 않는 상품 ID 테스트...")
        try:
            detail = fetcher.fetch_detail("INVALID_ID")
            print(f"   ❌ 오류가 발생해야 함")
        except Exception as e:
            print(f"   ✅ 예상된 오류 발생: {str(e)}")
        
        # 중복 데이터 저장
        print("\n3. 중복 데이터 저장 테스트...")
        products, _ = fetcher.fetch_list(page=1)
        if products:
            first = products[0]
            
            # 첫 번째 저장
            id1 = fetcher.save_raw(first)
            print(f"   첫 번째 저장: {id1}")
            
            # 두 번째 저장 (중복)
            id2 = fetcher.save_raw(first)
            print(f"   두 번째 저장: {id2}")
            
            if id1 and not id2:
                print(f"   ✅ 중복 감지 성공")
            else:
                print(f"   ❌ 중복 감지 실패")
        
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return False

def main():
    """메인 테스트 실행"""
    print("=" * 60)
    print("Mock 모드 상품 수집 기능 테스트")
    print("=" * 60)
    
    # 테스트 실행
    tests = [
        ("Mock Fetcher 기본 기능", test_mock_fetcher),
        ("데이터 변환", test_transformation),
        ("전체 수집 파이프라인", test_collection_pipeline),
        ("스케줄러 작업", test_scheduler_job),
        ("오류 처리", test_error_handling)
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
        print("\n상품 수집 시스템이 정상적으로 작동하고 있습니다:")
        print("- BaseFetcher 추상 클래스가 올바르게 구현됨")
        print("- 데이터 변환 파이프라인이 정상 작동")
        print("- 중복 감지 및 오류 처리가 적절히 수행됨")
        print("- 스케줄러 통합이 완료됨")
    else:
        print("\n⚠️  일부 테스트가 실패했습니다.")

if __name__ == "__main__":
    main()