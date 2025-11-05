"""
Error handling and logging configuration for Life360 application.
"""
import logging
import traceback
from typing import Optional, Dict, Any
from flask import Flask, render_template, request, jsonify, current_app
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
except ImportError:
    sentry_sdk = None
    FlaskIntegration = None
    SqlalchemyIntegration = None


class ErrorHandler:
    """Centralized error handling."""
    
    @staticmethod
    def init_app(app: Flask, sentry_dsn: Optional[str] = None):
        """Initialize error handling for the app."""
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(name)s: %(message)s',
            handlers=[
                logging.FileHandler('app.log'),
                logging.StreamHandler()
            ]
        )
        
        # Configure Sentry for production error tracking
        if sentry_dsn and not app.debug and sentry_sdk is not None:
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[
                    FlaskIntegration(),
                    SqlalchemyIntegration(),
                ],
                traces_sample_rate=0.1,
                environment=app.config.get('ENVIRONMENT', 'production')
            )
        
        # Register error handlers
        ErrorHandler._register_error_handlers(app)
    
    @staticmethod
    def _register_error_handlers(app: Flask):
        """Register error handlers with Flask app."""
        
        @app.errorhandler(400)
        def bad_request(error):
            return ErrorHandler._handle_error(error, "Bad Request", 400)
        
        @app.errorhandler(401)
        def unauthorized(error):
            return ErrorHandler._handle_error(error, "Unauthorized", 401)
        
        @app.errorhandler(403)
        def forbidden(error):
            return ErrorHandler._handle_error(error, "Forbidden", 403)
        
        @app.errorhandler(404)
        def not_found(error):
            return ErrorHandler._handle_error(error, "Page Not Found", 404)
        
        @app.errorhandler(405)
        def method_not_allowed(error):
            return ErrorHandler._handle_error(error, "Method Not Allowed", 405)
        
        @app.errorhandler(429)
        def too_many_requests(error):
            return ErrorHandler._handle_error(error, "Too Many Requests", 429)
        
        @app.errorhandler(500)
        def internal_error(error):
            return ErrorHandler._handle_error(error, "Internal Server Error", 500)
        
        @app.errorhandler(502)
        def bad_gateway(error):
            return ErrorHandler._handle_error(error, "Bad Gateway", 502)
        
        @app.errorhandler(503)
        def service_unavailable(error):
            return ErrorHandler._handle_error(error, "Service Unavailable", 503)
        
        @app.errorhandler(SQLAlchemyError)
        def handle_sqlalchemy_error(error):
            current_app.logger.error(f"Database error: {error}")
            return ErrorHandler._handle_error(error, "Database Error", 500)
        
        @app.errorhandler(IntegrityError)
        def handle_integrity_error(error):
            current_app.logger.error(f"Database integrity error: {error}")
            return ErrorHandler._handle_error(error, "Data Integrity Error", 400)
        
        @app.errorhandler(Exception)
        def handle_unexpected_error(error):
            current_app.logger.error(f"Unexpected error: {error}")
            current_app.logger.error(traceback.format_exc())
            return ErrorHandler._handle_error(error, "Unexpected Error", 500)
    
    @staticmethod
    def _handle_error(error: Exception, message: str, status_code: int) -> tuple:
        """Handle error and return appropriate response."""
        
        # Log the error
        current_app.logger.error(f"{message}: {error}")
        
        # Determine if request expects JSON
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'error': message,
                'status_code': status_code,
                'details': str(error) if current_app.debug else None
            }), status_code
        
        # Return HTML error page
        return render_template('error.html', 
                             error_code=status_code,
                             error_message=message,
                             error_details=str(error) if current_app.debug else None), status_code


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class BusinessLogicError(Exception):
    """Custom exception for business logic errors."""
    pass


class SecurityError(Exception):
    """Custom exception for security-related errors."""
    pass


def log_user_action(user_id: str, action: str, details: Optional[Dict[str, Any]] = None):
    """Log user actions for audit trail."""
    current_app.logger.info(f"User {user_id} performed action: {action}", extra={
        'user_id': user_id,
        'action': action,
        'details': details or {},
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', '')
    })


def log_security_event(event_type: str, details: Optional[Dict[str, Any]] = None):
    """Log security events."""
    current_app.logger.warning(f"Security event: {event_type}", extra={
        'event_type': event_type,
        'details': details or {},
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', '')
    })


def log_performance_metric(metric_name: str, value: float, unit: str = 'ms'):
    """Log performance metrics."""
    current_app.logger.info(f"Performance metric: {metric_name}={value}{unit}", extra={
        'metric_name': metric_name,
        'value': value,
        'unit': unit
    })



