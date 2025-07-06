#!/usr/bin/env python3
"""
드랍쉬핑 자동화 시스템 메인 엔트리 포인트
"""
import click
from loguru import logger


@click.group()
def cli():
    """드랍쉬핑 자동화 시스템 CLI"""
    pass


from dropshipping.storage.supabase_storage import SupabaseStorage
from dropshipping.suppliers.registry import SupplierRegistry


@cli.command()
@click.option("--supplier", required=True, help="공급사 이름 (domeme, ownerclan, zentrade)")
@click.option("--dry-run", is_flag=True, help="실제 실행 없이 테스트만 수행")
def fetch(supplier: str, dry_run: bool):
    """공급사로부터 상품 데이터 수집"""
    logger.info(f"상품 수집 시작: {supplier} (dry_run={dry_run})")
    
    storage = SupabaseStorage()
    registry = SupplierRegistry()
    
    try:
        fetcher = registry.get_supplier(supplier, storage)
        if dry_run:
            logger.info(f"[Dry Run] {supplier} Fetcher가 성공적으로 로드되었습니다.")
        else:
            # TODO: supplier_id를 DB에서 가져오도록 수정 필요
            fetcher.run_incremental(supplier_id=supplier)
            
    except ValueError as e:
        logger.error(e)
        return
    except Exception as e:
        logger.error(f"데이터 수집 중 예외 발생: {e}")
        return

    logger.info("상품 수집 완료")


@cli.command()
@click.option("--marketplace", help="마켓플레이스 이름")
@click.option("--account", help="계정 ID")
def upload(marketplace: str, account: str):
    """마켓플레이스에 상품 업로드"""
    logger.info(f"상품 업로드 시작: {marketplace} (account={account})")
    # TODO: Uploader 구현 후 연결
    logger.info("상품 업로드 완료")


@cli.command()
def process():
    """수집된 상품 데이터 AI 처리"""
    logger.info("AI 처리 시작")
    # TODO: AI Processor 구현 후 연결
    logger.info("AI 처리 완료")


@cli.command()
def schedule():
    """스케줄러 실행"""
    logger.info("스케줄러 시작")
    # TODO: Scheduler 구현 후 연결


if __name__ == "__main__":
    cli()
