#!/bin/bash
# 가상환경 활성화 스크립트

echo "🚀 드랍쉬핑 자동화 시스템 개발 환경 활성화"
echo ""

# 가상환경 활성화
source venv/bin/activate

echo "✅ 가상환경 활성화 완료"
echo "📍 Python 버전: $(python --version)"
echo ""
echo "🛠️  유용한 명령어:"
echo "  pytest                    # 전체 테스트 실행"
echo "  pytest -v                 # 상세 테스트 실행"
echo "  python -m dropshipping.main  # CLI 실행"
echo "  black dropshipping tests  # 코드 포맷팅"
echo "  ruff check dropshipping   # 린팅"
echo ""
echo "📚 문서:"
echo "  README.md                 # 프로젝트 개요"
echo "  DEVELOPMENT.md            # 개발 진행 상황"
echo "  docs/dropshipping_prd_v_1.md  # PRD"
echo ""