"""
모니터링 대시보드
실시간 시스템 상태 모니터링
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .alerts import AlertLevel, alert_manager
from .logger import get_logger
from .metrics import global_metrics

logger = get_logger(__name__)


class DashboardServer:
    """대시보드 서버"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Dropshipping Monitoring Dashboard")
        self.websockets: List[WebSocket] = []

        # 라우트 설정
        self._setup_routes()

        # 백그라운드 태스크
        self._update_task = None

    def _setup_routes(self):
        """라우트 설정"""

        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """대시보드 페이지"""
            return self._get_dashboard_html()

        @self.app.get("/api/metrics")
        async def get_metrics():
            """메트릭 조회"""
            return global_metrics.get_summary()

        @self.app.get("/api/alerts")
        async def get_alerts(
            level: Optional[str] = None, source: Optional[str] = None, hours: int = 24
        ):
            """알림 조회"""
            since = datetime.now() - timedelta(hours=hours)
            level_enum = AlertLevel(level) if level else None

            alerts = alert_manager.get_alert_history(level=level_enum, source=source, since=since)

            return {
                "alerts": [a.to_dict() for a in alerts],
                "summary": alert_manager.get_alert_summary(),
            }

        @self.app.get("/api/system")
        async def get_system_info():
            """시스템 정보"""

            # 스케줄러 정보 (있다면)
            scheduler_info = {}
            try:
                # 글로벌 스케줄러 인스턴스가 있다면
                if hasattr(self, "_scheduler"):
                    scheduler_info = self._scheduler.scheduler.get_schedule_summary()
            except:
                pass

            return {
                "timestamp": datetime.now().isoformat(),
                "metrics": global_metrics.get_summary(),
                "alerts": alert_manager.get_alert_summary(),
                "scheduler": scheduler_info,
            }

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """웹소켓 엔드포인트"""
            await websocket.accept()
            self.websockets.append(websocket)

            try:
                while True:
                    # 클라이언트 메시지 대기
                    data = await websocket.receive_text()
                    # 필요시 메시지 처리

            except WebSocketDisconnect:
                self.websockets.remove(websocket)

    async def _broadcast_updates(self):
        """실시간 업데이트 브로드캐스트"""
        while True:
            try:
                # 30초마다 업데이트
                await asyncio.sleep(30)

                # 현재 상태
                update = {
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "metrics": global_metrics.get_summary(),
                    "recent_alerts": [
                        a.to_dict() for a in alert_manager.get_alert_history(limit=5)
                    ],
                }

                # 모든 웹소켓으로 전송
                disconnected = []
                for ws in self.websockets:
                    try:
                        await ws.send_json(update)
                    except:
                        disconnected.append(ws)

                # 연결 끊긴 소켓 제거
                for ws in disconnected:
                    self.websockets.remove(ws)

            except Exception as e:
                logger.error(f"브로드캐스트 오류: {str(e)}")

    def _get_dashboard_html(self) -> str:
        """대시보드 HTML"""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Dropshipping Monitoring Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .header { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .header h1 { font-size: 24px; margin-bottom: 10px; }
        .header .status { display: flex; gap: 20px; font-size: 14px; color: #666; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { font-size: 18px; margin-bottom: 15px; color: #444; }
        .metric { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #666; }
        .metric-value { font-weight: 600; }
        .alert { padding: 10px; margin-bottom: 10px; border-radius: 4px; font-size: 14px; }
        .alert.info { background: #e3f2fd; color: #1976d2; }
        .alert.warning { background: #fff3e0; color: #f57c00; }
        .alert.error { background: #ffebee; color: #c62828; }
        .alert.critical { background: #f3e5f5; color: #6a1b9a; }
        .chart { height: 200px; margin-top: 10px; }
        .status-indicator { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .status-indicator.online { background: #4caf50; }
        .status-indicator.offline { background: #f44336; }
        .timestamp { font-size: 12px; color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Dropshipping Monitoring Dashboard</h1>
            <div class="status">
                <div><span class="status-indicator online"></span>System Status: <strong>Online</strong></div>
                <div>Last Update: <span id="last-update" class="timestamp">-</span></div>
                <div>WebSocket: <span id="ws-status">Connecting...</span></div>
            </div>
        </div>
        
        <div class="grid">
            <!-- 시스템 메트릭 -->
            <div class="card">
                <h2>📊 System Metrics</h2>
                <div id="system-metrics">
                    <div class="metric">
                        <span class="metric-label">API Requests</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">API Errors</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Avg Latency</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">DB Queries</span>
                        <span class="metric-value">-</span>
                    </div>
                </div>
            </div>
            
            <!-- 비즈니스 메트릭 -->
            <div class="card">
                <h2>💼 Business Metrics</h2>
                <div id="business-metrics">
                    <div class="metric">
                        <span class="metric-label">Products Fetched</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Products Processed</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Products Uploaded</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Orders Processed</span>
                        <span class="metric-value">-</span>
                    </div>
                </div>
            </div>
            
            <!-- AI 메트릭 -->
            <div class="card">
                <h2>🤖 AI Metrics</h2>
                <div id="ai-metrics">
                    <div class="metric">
                        <span class="metric-label">Total Requests</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Tokens Used</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Cost</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Avg Latency</span>
                        <span class="metric-value">-</span>
                    </div>
                </div>
            </div>
            
            <!-- 최근 알림 -->
            <div class="card" style="grid-column: span 2;">
                <h2>🔔 Recent Alerts</h2>
                <div id="recent-alerts">
                    <p style="color: #999;">No alerts</p>
                </div>
            </div>
            
            <!-- 알림 요약 -->
            <div class="card">
                <h2>📈 Alert Summary</h2>
                <div id="alert-summary">
                    <div class="metric">
                        <span class="metric-label">Total Alerts</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Hour</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Critical</span>
                        <span class="metric-value">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Errors</span>
                        <span class="metric-value">-</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws = null;
        
        // WebSocket 연결
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                document.getElementById('ws-status').textContent = 'Connected';
                document.getElementById('ws-status').style.color = '#4caf50';
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'update') {
                    updateDashboard(data);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('ws-status').textContent = 'Disconnected';
                document.getElementById('ws-status').style.color = '#f44336';
                // 재연결 시도
                setTimeout(connectWebSocket, 5000);
            };
        }
        
        // 대시보드 업데이트
        function updateDashboard(data) {
            // 타임스탬프 업데이트
            document.getElementById('last-update').textContent = 
                new Date(data.timestamp).toLocaleString();
            
            // 메트릭 업데이트
            if (data.metrics) {
                updateMetrics(data.metrics);
            }
            
            // 알림 업데이트
            if (data.recent_alerts) {
                updateAlerts(data.recent_alerts);
            }
        }
        
        // 메트릭 업데이트
        function updateMetrics(metrics) {
            // 시스템 메트릭
            const systemMetrics = document.getElementById('system-metrics');
            systemMetrics.innerHTML = `
                <div class="metric">
                    <span class="metric-label">API Requests</span>
                    <span class="metric-value">${metrics.system.api.total_requests.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">API Errors</span>
                    <span class="metric-value">${metrics.system.api.total_errors} (${(metrics.system.api.error_rate * 100).toFixed(1)}%)</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Latency</span>
                    <span class="metric-value">${metrics.system.api.latency.mean ? metrics.system.api.latency.mean.toFixed(3) + 's' : '-'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">DB Queries</span>
                    <span class="metric-value">${metrics.system.db.total_queries.toLocaleString()}</span>
                </div>
            `;
            
            // 비즈니스 메트릭
            const businessMetrics = document.getElementById('business-metrics');
            businessMetrics.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Products Fetched</span>
                    <span class="metric-value">${metrics.business.products.fetched.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Products Processed</span>
                    <span class="metric-value">${metrics.business.products.processed.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Products Uploaded</span>
                    <span class="metric-value">${metrics.business.products.uploaded.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Orders Processed</span>
                    <span class="metric-value">${metrics.business.orders.processed.toLocaleString()}</span>
                </div>
            `;
            
            // AI 메트릭
            const aiMetrics = document.getElementById('ai-metrics');
            aiMetrics.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Total Requests</span>
                    <span class="metric-value">${metrics.ai.total_requests.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Tokens Used</span>
                    <span class="metric-value">${metrics.ai.total_tokens.toLocaleString()}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Cost</span>
                    <span class="metric-value">$${metrics.ai.total_cost.toFixed(2)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Latency</span>
                    <span class="metric-value">${metrics.ai.latency.mean ? metrics.ai.latency.mean.toFixed(3) + 's' : '-'}</span>
                </div>
            `;
        }
        
        // 알림 업데이트
        function updateAlerts(alerts) {
            const alertsContainer = document.getElementById('recent-alerts');
            
            if (alerts.length === 0) {
                alertsContainer.innerHTML = '<p style="color: #999;">No alerts</p>';
                return;
            }
            
            alertsContainer.innerHTML = alerts.map(alert => `
                <div class="alert ${alert.level}">
                    <strong>${alert.title}</strong><br>
                    ${alert.message}<br>
                    <span class="timestamp">${new Date(alert.timestamp).toLocaleString()}</span>
                </div>
            `).join('');
        }
        
        // 초기 데이터 로드
        async function loadInitialData() {
            try {
                const response = await fetch('/api/system');
                const data = await response.json();
                updateDashboard(data);
                
                // 알림 요약 업데이트
                if (data.alerts) {
                    const summary = document.getElementById('alert-summary');
                    summary.innerHTML = `
                        <div class="metric">
                            <span class="metric-label">Total Alerts</span>
                            <span class="metric-value">${data.alerts.total_alerts}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Last Hour</span>
                            <span class="metric-value">${data.alerts.last_hour}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Critical</span>
                            <span class="metric-value">${data.alerts.by_level.critical || 0}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Errors</span>
                            <span class="metric-value">${data.alerts.by_level.error || 0}</span>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Failed to load initial data:', error);
            }
        }
        
        // 페이지 로드 시 실행
        document.addEventListener('DOMContentLoaded', () => {
            connectWebSocket();
            loadInitialData();
            
            // 주기적 업데이트 (웹소켓 백업)
            setInterval(loadInitialData, 60000);
        });
    </script>
</body>
</html>
"""

    def start(self):
        """서버 시작"""
        # 백그라운드 태스크 시작
        self._update_task = asyncio.create_task(self._broadcast_updates())

        # 서버 시작
        logger.info(f"대시보드 서버 시작: http://{self.host}:{self.port}")
        uvicorn.run(self.app, host=self.host, port=self.port)

    async def stop(self):
        """서버 중지"""
        if self._update_task:
            self._update_task.cancel()

        # 모든 웹소켓 연결 종료
        for ws in self.websockets:
            await ws.close()

        logger.info("대시보드 서버 중지됨")
