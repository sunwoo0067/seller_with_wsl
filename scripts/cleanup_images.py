#!/usr/bin/env python
"""
처리된 이미지 정리 스크립트
오래된 AI 처리 이미지를 삭제하여 디스크 공간 확보
"""

import click
from pathlib import Path
from datetime import datetime, timedelta
import time

from dropshipping.ai_processors.image_processor import ImageProcessor
from dropshipping.ai_processors.model_router import ModelRouter


@click.command()
@click.option(
    '--days',
    default=7,
    help='이 일수보다 오래된 이미지 삭제 (기본: 7일)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='실제로 삭제하지 않고 삭제할 파일만 표시'
)
@click.option(
    '--output-dir',
    default='./processed_images',
    help='처리된 이미지 디렉터리 경로'
)
def cleanup_images(days: int, dry_run: bool, output_dir: str):
    """오래된 처리 이미지 정리"""
    
    click.echo(f"=== 이미지 정리 작업 시작 ===")
    click.echo(f"- 디렉터리: {output_dir}")
    click.echo(f"- 기준: {days}일 이상 된 파일")
    click.echo(f"- 모드: {'시뮬레이션' if dry_run else '실제 삭제'}\n")
    
    # 디렉터리 확인
    output_path = Path(output_dir)
    if not output_path.exists():
        click.echo(f"❌ 디렉터리가 존재하지 않습니다: {output_dir}")
        return
    
    # 파일 검색
    current_time = time.time()
    cutoff_time = current_time - (days * 24 * 60 * 60)
    
    total_size = 0
    files_to_delete = []
    
    for file_path in output_path.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            if stat.st_mtime < cutoff_time:
                files_to_delete.append({
                    'path': file_path,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime)
                })
                total_size += stat.st_size
    
    if not files_to_delete:
        click.echo("✅ 삭제할 파일이 없습니다.")
        return
    
    # 삭제할 파일 목록 표시
    click.echo(f"📁 삭제 대상 파일: {len(files_to_delete)}개")
    click.echo(f"💾 총 크기: {total_size / 1024 / 1024:.2f} MB\n")
    
    # 상위 10개 파일 표시
    for i, file_info in enumerate(files_to_delete[:10]):
        click.echo(
            f"  - {file_info['path'].name} "
            f"({file_info['size'] / 1024:.1f} KB, "
            f"{file_info['modified'].strftime('%Y-%m-%d %H:%M')})"
        )
    
    if len(files_to_delete) > 10:
        click.echo(f"  ... 외 {len(files_to_delete) - 10}개")
    
    # 삭제 실행
    if not dry_run:
        click.echo("\n삭제 중...")
        
        with click.progressbar(files_to_delete, label='파일 삭제') as files:
            for file_info in files:
                try:
                    file_info['path'].unlink()
                except Exception as e:
                    click.echo(f"\n❌ 삭제 실패: {file_info['path'].name} - {str(e)}")
        
        click.echo(f"\n✅ {len(files_to_delete)}개 파일 삭제 완료!")
        click.echo(f"💾 확보된 공간: {total_size / 1024 / 1024:.2f} MB")
    else:
        click.echo("\n💡 실제로 삭제하려면 --dry-run 옵션을 제거하고 다시 실행하세요.")
    
    # ImageProcessor의 cleanup 메서드도 사용 가능
    if not dry_run:
        click.echo("\n=== ImageProcessor cleanup 메서드 사용 ===")
        
        router = ModelRouter()
        processor = ImageProcessor(model_router=router)
        processor.output_dir = output_path
        
        removed = processor.cleanup_processed_images(days=days)
        click.echo(f"✅ ImageProcessor로 {removed}개 파일 추가 정리")


if __name__ == '__main__':
    cleanup_images()