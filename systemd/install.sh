#!/bin/bash
# systemd 서비스 설치 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Root 권한 확인
if [[ $EUID -ne 0 ]]; then
   log_error "이 스크립트는 root 권한으로 실행해야 합니다."
   exit 1
fi

# 설치 디렉토리
INSTALL_DIR="/opt/dropshipping"
SERVICE_DIR="/etc/systemd/system"
USER="dropshipping"
GROUP="dropshipping"

log_info "드랍쉬핑 자동화 시스템 설치를 시작합니다..."

# 사용자 생성
if ! id "$USER" &>/dev/null; then
    log_info "시스템 사용자 생성: $USER"
    useradd -r -s /bin/false -d "$INSTALL_DIR" -m "$USER"
else
    log_info "사용자가 이미 존재합니다: $USER"
fi

# 디렉토리 생성
log_info "디렉토리 생성..."
mkdir -p "$INSTALL_DIR"/{logs,data,backups}
mkdir -p "$SERVICE_DIR"

# 소스 코드 복사
log_info "소스 코드 복사..."
cp -r dropshipping "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"
cp .env.example "$INSTALL_DIR/.env"

# 권한 설정
log_info "권한 설정..."
chown -R "$USER:$GROUP" "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/.env"

# Python 가상환경 생성
log_info "Python 가상환경 생성..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
log_info "Python 패키지 설치..."
pip install --upgrade pip
pip install -r requirements.txt

# systemd 서비스 파일 복사
log_info "systemd 서비스 설치..."
cp systemd/*.service "$SERVICE_DIR/"

# systemd 서비스 파일 수정 (Python 경로 업데이트)
sed -i "s|/usr/bin/python3|$INSTALL_DIR/venv/bin/python|g" "$SERVICE_DIR"/dropshipping-*.service

# systemd 리로드
log_info "systemd 데몬 리로드..."
systemctl daemon-reload

# 서비스 활성화
log_info "서비스 활성화..."
systemctl enable dropshipping-api.service
systemctl enable dropshipping-scheduler.service
systemctl enable dropshipping-monitoring.service

log_info "설치가 완료되었습니다!"
echo ""
echo "다음 단계:"
echo "1. $INSTALL_DIR/.env 파일을 편집하여 환경 변수를 설정하세요"
echo "2. 서비스를 시작하세요:"
echo "   systemctl start dropshipping-api"
echo "   systemctl start dropshipping-scheduler"
echo "   systemctl start dropshipping-monitoring"
echo "3. 서비스 상태 확인:"
echo "   systemctl status dropshipping-api"
echo "   systemctl status dropshipping-scheduler"
echo "   systemctl status dropshipping-monitoring"
echo "4. 로그 확인:"
echo "   journalctl -u dropshipping-api -f"
echo "   journalctl -u dropshipping-scheduler -f"
echo "   journalctl -u dropshipping-monitoring -f"