"""
Monitoring and health check system for Life360 application.
"""
import time
import psutil
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import requests
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    name: str
    status: str  # 'healthy', 'unhealthy', 'degraded'
    message: str
    response_time_ms: float
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class HealthChecker:
    """Performs health checks on various system components."""
    
    def __init__(self, app: Flask, db: SQLAlchemy):
        self.app = app
        self.db = db
        self.checks: List[callable] = [
            self.check_database,
            self.check_disk_space,
            self.check_memory,
            self.check_cpu,
            self.check_azure_auth,
            self.check_sms_service,
            self.check_openrouter_service
        ]
    
    def check_database(self) -> HealthCheckResult:
        """Check database connectivity and performance."""
        start_time = time.time()
        
        try:
            with self.db.engine.connect() as conn:
                # Test basic connectivity
                result = conn.execute(text("SELECT 1")).fetchone()
                
                if not result or result[0] != 1:
                    return HealthCheckResult(
                        name="database",
                        status="unhealthy",
                        message="Database query returned unexpected result",
                        response_time_ms=(time.time() - start_time) * 1000
                    )
                
                # Test performance with a more complex query
                conn.execute(text("SELECT COUNT(*) FROM sqlite_master"))
                
                response_time = (time.time() - start_time) * 1000
                
                return HealthCheckResult(
                    name="database",
                    status="healthy",
                    message="Database is responding normally",
                    response_time_ms=response_time,
                    details={
                        "response_time_ms": response_time,
                        "connection_pool_size": self.db.engine.pool.size(),
                        "checked_out_connections": self.db.engine.pool.checkedout()
                    }
                )
                
        except Exception as e:
            return HealthCheckResult(
                name="database",
                status="unhealthy",
                message=f"Database connection failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_disk_space(self) -> HealthCheckResult:
        """Check available disk space."""
        start_time = time.time()
        
        try:
            # Get disk usage for the current directory
            disk_usage = psutil.disk_usage('.')
            
            total_gb = disk_usage.total / (1024**3)
            free_gb = disk_usage.free / (1024**3)
            used_percent = (disk_usage.used / disk_usage.total) * 100
            
            # Determine status based on free space
            if used_percent > 90:
                status = "unhealthy"
                message = "Disk space critically low"
            elif used_percent > 80:
                status = "degraded"
                message = "Disk space running low"
            else:
                status = "healthy"
                message = "Disk space is adequate"
            
            return HealthCheckResult(
                name="disk_space",
                status=status,
                message=message,
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "total_gb": round(total_gb, 2),
                    "free_gb": round(free_gb, 2),
                    "used_percent": round(used_percent, 2)
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="disk_space",
                status="unhealthy",
                message=f"Failed to check disk space: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_memory(self) -> HealthCheckResult:
        """Check system memory usage."""
        start_time = time.time()
        
        try:
            memory = psutil.virtual_memory()
            
            total_gb = memory.total / (1024**3)
            available_gb = memory.available / (1024**3)
            used_percent = memory.percent
            
            # Determine status based on memory usage
            if used_percent > 90:
                status = "unhealthy"
                message = "Memory usage critically high"
            elif used_percent > 80:
                status = "degraded"
                message = "Memory usage is high"
            else:
                status = "healthy"
                message = "Memory usage is normal"
            
            return HealthCheckResult(
                name="memory",
                status=status,
                message=message,
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "total_gb": round(total_gb, 2),
                    "available_gb": round(available_gb, 2),
                    "used_percent": round(used_percent, 2)
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="memory",
                status="unhealthy",
                message=f"Failed to check memory: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_cpu(self) -> HealthCheckResult:
        """Check CPU usage."""
        start_time = time.time()
        
        try:
            # Get CPU usage over 1 second
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Determine status based on CPU usage
            if cpu_percent > 90:
                status = "unhealthy"
                message = "CPU usage critically high"
            elif cpu_percent > 80:
                status = "degraded"
                message = "CPU usage is high"
            else:
                status = "healthy"
                message = "CPU usage is normal"
            
            return HealthCheckResult(
                name="cpu",
                status=status,
                message=message,
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "cpu_percent": round(cpu_percent, 2),
                    "cpu_count": cpu_count
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="cpu",
                status="unhealthy",
                message=f"Failed to check CPU: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_azure_auth(self) -> HealthCheckResult:
        """Check Azure AD authentication service."""
        start_time = time.time()
        
        try:
            # Check if Azure configuration is present
            client_id = self.app.config.get('AZURE_CLIENT_ID')
            if not client_id:
                return HealthCheckResult(
                    name="azure_auth",
                    status="degraded",
                    message="Azure AD not configured",
                    response_time_ms=(time.time() - start_time) * 1000
                )
            
            # Test Azure AD endpoint connectivity
            authority = self.app.config.get('AZURE_AUTHORITY', 'https://login.microsoftonline.com/common')
            test_url = f"{authority}/.well-known/openid_configuration"
            
            response = requests.get(test_url, timeout=5)
            response.raise_for_status()
            
            return HealthCheckResult(
                name="azure_auth",
                status="healthy",
                message="Azure AD service is accessible",
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "authority": authority,
                    "response_status": response.status_code
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="azure_auth",
                status="unhealthy",
                message=f"Azure AD service check failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_sms_service(self) -> HealthCheckResult:
        """Check SMS service connectivity."""
        start_time = time.time()
        
        try:
            # Check if SMS configuration is present
            username = self.app.config.get('MYMOBILEAPI_USERNAME')
            if not username:
                return HealthCheckResult(
                    name="sms_service",
                    status="degraded",
                    message="SMS service not configured",
                    response_time_ms=(time.time() - start_time) * 1000
                )
            
            # Test SMS service endpoint
            sms_url = self.app.config.get('MYMOBILEAPI_URL', 'https://rest.mymobileapi.com/v3/BulkMessages')
            
            # Just check if the endpoint is reachable
            response = requests.head(sms_url, timeout=5)
            
            return HealthCheckResult(
                name="sms_service",
                status="healthy",
                message="SMS service is accessible",
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "sms_url": sms_url,
                    "response_status": response.status_code
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="sms_service",
                status="unhealthy",
                message=f"SMS service check failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def check_openrouter_service(self) -> HealthCheckResult:
        """Check AI service (Puter) connectivity."""
        start_time = time.time()
        
        try:
            # Test Puter's free AI service endpoint
            puter_url = 'https://puter-llm-proxy.puter.com/v1/chat/completions'
            
            # Just check if the endpoint is reachable
            response = requests.head(puter_url, timeout=5)
            
            return HealthCheckResult(
                name="ai_service",
                status="healthy",
                message="Puter AI service is accessible",
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "puter_url": puter_url,
                    "response_status": response.status_code
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="ai_service",
                status="unhealthy",
                message=f"AI service check failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all health checks."""
        results = []
        
        for check in self.checks:
            try:
                result = check()
                results.append(result)
            except Exception as e:
                logger.error(f"Health check {check.__name__} failed: {e}")
                results.append(HealthCheckResult(
                    name=check.__name__.replace('check_', ''),
                    status="unhealthy",
                    message=f"Health check failed: {str(e)}",
                    response_time_ms=0
                ))
        
        return results
    
    def get_overall_status(self, results: List[HealthCheckResult]) -> str:
        """Determine overall system status."""
        if not results:
            return "unknown"
        
        unhealthy_count = sum(1 for r in results if r.status == "unhealthy")
        degraded_count = sum(1 for r in results if r.status == "degraded")
        
        if unhealthy_count > 0:
            return "unhealthy"
        elif degraded_count > 0:
            return "degraded"
        else:
            return "healthy"


class MetricsCollector:
    """Collects application metrics."""
    
    def __init__(self, app: Flask, db: SQLAlchemy):
        self.app = app
        self.db = db
        self.metrics: Dict[str, Any] = {}
    
    def collect_metrics(self) -> Dict[str, Any]:
        """Collect all application metrics."""
        try:
            from app import Order, Practitioner, StockItem, StockUnit
            
            # Database metrics
            total_orders = Order.query.count()
            completed_orders = Order.query.filter(Order.status.ilike("%completed%")).count()
            pending_orders = total_orders - completed_orders
            
            total_practitioners = Practitioner.query.count()
            total_stock_items = StockItem.query.count()
            total_stock_units = StockUnit.query.count()
            
            # Application metrics
            uptime = time.time() - self.app.config.get('START_TIME', time.time())
            
            self.metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'uptime_seconds': uptime,
                'uptime_hours': uptime / 3600,
                'database': {
                    'total_orders': total_orders,
                    'completed_orders': completed_orders,
                    'pending_orders': pending_orders,
                    'total_practitioners': total_practitioners,
                    'total_stock_items': total_stock_items,
                    'total_stock_units': total_stock_units
                },
                'system': {
                    'cpu_percent': psutil.cpu_percent(),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_percent': psutil.disk_usage('.').percent
                }
            }
            
            return self.metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            return {'error': str(e)}


def create_health_endpoints(app: Flask, db: SQLAlchemy):
    """Create health check endpoints."""
    
    health_checker = HealthChecker(app, db)
    metrics_collector = MetricsCollector(app, db)
    
    @app.route('/health')
    def health():
        """Basic health check endpoint."""
        try:
            # Quick database check
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'version': '1.0.0'
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 500
    
    @app.route('/health/detailed')
    def detailed_health():
        """Detailed health check endpoint."""
        results = health_checker.run_all_checks()
        overall_status = health_checker.get_overall_status(results)
        
        # Determine HTTP status code
        if overall_status == "healthy":
            status_code = 200
        elif overall_status == "degraded":
            status_code = 200  # Still operational
        else:
            status_code = 503  # Service unavailable
        
        return jsonify({
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': [asdict(result) for result in results],
            'summary': {
                'total_checks': len(results),
                'healthy': sum(1 for r in results if r.status == "healthy"),
                'degraded': sum(1 for r in results if r.status == "degraded"),
                'unhealthy': sum(1 for r in results if r.status == "unhealthy")
            }
        }), status_code
    
    @app.route('/metrics')
    def metrics():
        """Application metrics endpoint."""
        metrics_data = metrics_collector.collect_metrics()
        return jsonify(metrics_data), 200
    
    @app.route('/ready')
    def readiness():
        """Kubernetes readiness probe endpoint."""
        try:
            # Check if application is ready to serve traffic
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            return jsonify({
                'status': 'ready',
                'timestamp': datetime.utcnow().isoformat()
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'not_ready',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 503
    
    @app.route('/live')
    def liveness():
        """Kubernetes liveness probe endpoint."""
        # Simple liveness check - if the app is running, it's alive
        return jsonify({
            'status': 'alive',
            'timestamp': datetime.utcnow().isoformat()
        }), 200



