# 드랍쉬핑 자동화 시스템 배포 가이드

## 목차

1. [시스템 요구사항](#시스템-요구사항)
2. [배포 방법](#배포-방법)
   - [Docker Compose 배포](#docker-compose-배포)
   - [Systemd 서비스 배포](#systemd-서비스-배포)
   - [Kubernetes 배포](#kubernetes-배포)
3. [환경 설정](#환경-설정)
4. [SSL 인증서 설정](#ssl-인증서-설정)
5. [모니터링 설정](#모니터링-설정)
6. [백업 및 복구](#백업-및-복구)
7. [트러블슈팅](#트러블슈팅)

## 시스템 요구사항

### 최소 사양
- CPU: 2 코어
- RAM: 4GB
- 디스크: 20GB SSD
- OS: Ubuntu 20.04+ / Debian 11+

### 권장 사양
- CPU: 4 코어 이상
- RAM: 8GB 이상
- 디스크: 50GB+ SSD
- OS: Ubuntu 22.04 LTS

### 필수 소프트웨어
- Python 3.12+
- Docker 20.10+ & Docker Compose v2+
- Git
- Nginx (리버스 프록시용)
- PostgreSQL 14+ (Supabase 사용 시 불필요)

## 배포 방법

### Docker Compose 배포

#### 1. 소스 코드 클론
```bash
git clone https://github.com/yourusername/dropshipping-automation.git
cd dropshipping-automation
```

#### 2. 환경 변수 설정
```bash
cp .env.example .env
nano .env  # 환경 변수 편집
```

#### 3. Docker 이미지 빌드 및 실행
```bash
# 이미지 빌드
docker-compose build

# 백그라운드에서 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 서비스 상태 확인
docker-compose ps
```

#### 4. 서비스 접속
- API: http://localhost:8000
- API 문서: http://localhost:8000/docs
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### Systemd 서비스 배포

#### 1. 설치 스크립트 실행
```bash
sudo ./systemd/install.sh
```

#### 2. 환경 변수 설정
```bash
sudo nano /opt/dropshipping/.env
```

#### 3. 서비스 시작
```bash
# API 서버 시작
sudo systemctl start dropshipping-api
sudo systemctl status dropshipping-api

# 스케줄러 시작
sudo systemctl start dropshipping-scheduler
sudo systemctl status dropshipping-scheduler

# 모니터링 시작
sudo systemctl start dropshipping-monitoring
sudo systemctl status dropshipping-monitoring

# 부팅 시 자동 시작 설정
sudo systemctl enable dropshipping-api
sudo systemctl enable dropshipping-scheduler
sudo systemctl enable dropshipping-monitoring
```

#### 4. 로그 확인
```bash
# 실시간 로그 모니터링
sudo journalctl -u dropshipping-api -f
sudo journalctl -u dropshipping-scheduler -f
sudo journalctl -u dropshipping-monitoring -f

# 특정 시간 범위 로그
sudo journalctl -u dropshipping-api --since "1 hour ago"
```

### Kubernetes 배포

#### 1. 네임스페이스 생성
```bash
kubectl create namespace dropshipping
```

#### 2. 시크릿 생성
```bash
kubectl create secret generic dropshipping-env \
  --from-env-file=.env \
  -n dropshipping
```

#### 3. 배포
```bash
kubectl apply -f k8s/ -n dropshipping
```

#### 4. 상태 확인
```bash
kubectl get all -n dropshipping
kubectl logs -f deployment/dropshipping-api -n dropshipping
```

## 환경 설정

### 필수 환경 변수

```bash
# 환경 설정
ENV=production
LOG_LEVEL=INFO

# 데이터베이스
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
DATABASE_URL=postgresql://user:password@host:5432/dbname

# API 키
DOMEME_API_KEY=your-api-key
COUPANG_ACCESS_KEY=your-access-key
COUPANG_SECRET_KEY=your-secret-key
# ... 기타 API 키

# AI 모델
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# 알림
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### 성능 튜닝

```bash
# API 서버
WORKERS=4  # CPU 코어 수와 동일하게
MAX_CONNECTIONS=1000
REQUEST_TIMEOUT=60

# 스케줄러
SCHEDULER_WORKERS=2
SCHEDULER_MAX_INSTANCES=10

# 캐시
REDIS_MAX_MEMORY=1gb
CACHE_TTL=300
```

## SSL 인증서 설정

### Let's Encrypt 사용

```bash
# Certbot 설치
sudo apt update
sudo apt install certbot python3-certbot-nginx

# 인증서 발급
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# 자동 갱신 설정
sudo systemctl enable certbot.timer
```

### Docker Compose에서 SSL 설정

```yaml
# docker-compose.yml에 추가
nginx:
  volumes:
    - /etc/letsencrypt:/etc/letsencrypt:ro
    - ./nginx-ssl.conf:/etc/nginx/nginx.conf:ro
```

## 모니터링 설정

### Prometheus 설정

`prometheus.yml` 생성:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'dropshipping-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/api/v1/monitoring/metrics'

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
```

### Grafana 대시보드

1. Grafana 접속 (http://localhost:3000)
2. 데이터 소스 추가: Prometheus
3. 대시보드 임포트: `grafana/dashboards/` 디렉토리의 JSON 파일

### 알림 설정

```bash
# Slack 알림
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_CHANNEL=#dropshipping-alerts

# 이메일 알림
ALERT_EMAIL_TO=admin@company.com
ALERT_EMAIL_FROM=noreply@company.com
```

## 백업 및 복구

### 자동 백업 설정

```bash
# Cron 작업 추가
sudo crontab -e

# 매일 새벽 3시 백업
0 3 * * * docker exec dropshipping-api python -m dropshipping.backup --s3
```

### 수동 백업

```bash
# 데이터베이스 백업
docker exec dropshipping-api python -m dropshipping.backup \
  --type database \
  --output /backups/db-$(date +%Y%m%d-%H%M%S).sql

# 전체 백업
docker exec dropshipping-api python -m dropshipping.backup \
  --type full \
  --compress \
  --encrypt
```

### 복구

```bash
# 데이터베이스 복구
docker exec dropshipping-api python -m dropshipping.restore \
  --file /backups/db-20240101-030000.sql \
  --type database

# 전체 복구
docker exec dropshipping-api python -m dropshipping.restore \
  --file /backups/full-20240101-030000.tar.gz \
  --decrypt
```

## 트러블슈팅

### 일반적인 문제

#### 1. API 서버가 시작되지 않음
```bash
# 로그 확인
docker-compose logs api
sudo journalctl -u dropshipping-api -n 100

# 환경 변수 확인
docker exec dropshipping-api env | grep SUPABASE

# 포트 충돌 확인
sudo netstat -tlnp | grep 8000
```

#### 2. 데이터베이스 연결 실패
```bash
# 연결 테스트
docker exec dropshipping-api python -c "
from dropshipping.storage.supabase_storage import SupabaseStorage
storage = SupabaseStorage()
print(storage.client.table('products').select('*').limit(1).execute())
"

# Supabase 상태 확인
curl https://your-project.supabase.co/rest/v1/
```

#### 3. 메모리 부족
```bash
# 메모리 사용량 확인
docker stats

# 컨테이너 리소스 제한 조정
docker-compose down
# docker-compose.yml에서 메모리 제한 수정
docker-compose up -d
```

#### 4. 로그 파일 크기 문제
```bash
# 로그 정리
docker exec dropshipping-api find /app/logs -name "*.log" -mtime +7 -delete

# 로그 로테이션 설정
echo '/app/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}' | sudo tee /etc/logrotate.d/dropshipping
```

### 성능 최적화

#### 1. 느린 API 응답
```bash
# 슬로우 쿼리 확인
docker exec dropshipping-api python -m dropshipping.monitoring.analyze --slow-queries

# 인덱스 최적화
docker exec dropshipping-api python -m dropshipping.db.optimize
```

#### 2. 높은 CPU 사용률
```bash
# 프로세스 확인
docker exec dropshipping-api top

# 워커 수 조정
docker-compose scale api=4
```

### 보안 점검

```bash
# 보안 스캔
docker scan dropshipping-api:latest

# 취약점 확인
docker exec dropshipping-api pip-audit

# 시크릿 스캔
docker exec dropshipping-api gitleaks detect
```

## 업데이트 절차

### Docker Compose 업데이트
```bash
# 백업
docker exec dropshipping-api python -m dropshipping.backup --full

# 새 버전 가져오기
git pull origin main

# 이미지 재빌드
docker-compose build --no-cache

# 롤링 업데이트
docker-compose up -d --no-deps --build api
docker-compose up -d --no-deps --build scheduler

# 상태 확인
docker-compose ps
docker-compose logs -f
```

### Systemd 서비스 업데이트
```bash
# 백업
sudo -u dropshipping python -m dropshipping.backup --full

# 서비스 중지
sudo systemctl stop dropshipping-api dropshipping-scheduler

# 코드 업데이트
cd /opt/dropshipping
sudo -u dropshipping git pull origin main
sudo -u dropshipping pip install -r requirements.txt

# 서비스 재시작
sudo systemctl start dropshipping-api dropshipping-scheduler

# 상태 확인
sudo systemctl status dropshipping-api
```

## 지원

문제가 발생하면:
1. [이슈 트래커](https://github.com/yourusername/dropshipping-automation/issues) 확인
2. 로그 파일 수집: `/app/logs/` 또는 `journalctl`
3. 환경 정보 수집: `docker exec dropshipping-api python -m dropshipping.debug --info`