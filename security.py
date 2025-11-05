"""
Security utilities and validation for Life360 application.
"""
import re
try:
    import magic
except ImportError:
    magic = None
import secrets
from typing import Optional, List, Dict, Any
from werkzeug.utils import secure_filename
from flask import current_app
import bleach


class SecurityValidator:
    """Comprehensive input validation and sanitization."""
    
    # Allowed file extensions and MIME types
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "png", "jpg", "jpeg", "txt", "ppt", "pptx"}
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/csv',
        'image/png',
        'image/jpeg',
        'text/plain',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    }
    
    # Provider normalization map
    PROVIDER_MAP = {
        "Umvuzo Fedhealth": "Intelligene Fedhealth",
        "Umvuzo Intelligene": "Intelligene Umvuzo",
    }
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        if not email:
            return True  # Optional field
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            return True  # Optional field
        # Allow various international formats
        pattern = r'^[\+]?[1-9][\d]{0,15}$'
        return bool(re.match(pattern, phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')))
    
    @staticmethod
    def validate_name(name: str) -> bool:
        """Validate name fields."""
        if not name:
            return False
        # Allow letters, spaces, hyphens, apostrophes
        pattern = r'^[a-zA-Z\s\-\'\.]+$'
        return bool(re.match(pattern, name)) and len(name.strip()) >= 1
    
    @staticmethod
    def validate_sku(sku: str) -> bool:
        """Validate SKU format."""
        if not sku:
            return False
        # Allow alphanumeric, hyphens, underscores
        pattern = r'^[a-zA-Z0-9\-_]+$'
        return bool(re.match(pattern, sku)) and len(sku) <= 120
    
    @staticmethod
    def validate_barcode(barcode: str) -> bool:
        """Validate barcode format."""
        if not barcode:
            return False
        # Allow alphanumeric, hyphens, underscores
        pattern = r'^[a-zA-Z0-9\-_]+$'
        return bool(re.match(pattern, barcode)) and len(barcode) <= 120
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """Sanitize HTML content."""
        if not text:
            return ""
        # Allow basic formatting tags
        allowed_tags = ['b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li']
        return bleach.clean(text, tags=allowed_tags, strip=True)
    
    @staticmethod
    def validate_file_upload(file) -> tuple[bool, str]:
        """Validate uploaded file."""
        if not file or not file.filename:
            return False, "No file provided"
        
        # Check file extension
        if '.' not in file.filename:
            return False, "File must have an extension"
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in SecurityValidator.ALLOWED_EXTENSIONS:
            return False, f"File type .{ext} not allowed"
        
        # Check file size (10MB limit)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return False, "File too large (max 10MB)"
        
        # Check MIME type
        if magic is not None:
            try:
                file_content = file.read(1024)
                file.seek(0)  # Reset to beginning
                mime_type = magic.from_buffer(file_content, mime=True)
                if mime_type not in SecurityValidator.ALLOWED_MIME_TYPES:
                    return False, f"File type {mime_type} not allowed"
            except Exception:
                # If magic library fails, fall back to extension check
                pass
        else:
            # If magic library is not available, fall back to extension check
            pass
        
        return True, "Valid file"
    
    @staticmethod
    def normalize_provider(name: Optional[str]) -> Optional[str]:
        """Normalize provider names."""
        if not name:
            return name
        return SecurityValidator.PROVIDER_MAP.get(name, name)
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate CSRF token."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_csrf_token(token: str, session_token: str) -> bool:
        """Validate CSRF token."""
        return token and session_token and token == session_token


class InputValidator:
    """Input validation for forms."""
    
    @staticmethod
    def validate_order_data(data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate order form data."""
        errors = []
        
        # Required fields
        if not data.get('name', '').strip():
            errors.append("Customer name is required")
        elif not SecurityValidator.validate_name(data['name']):
            errors.append("Invalid customer name format")
        
        if not data.get('surname', '').strip():
            errors.append("Customer surname is required")
        elif not SecurityValidator.validate_name(data['surname']):
            errors.append("Invalid customer surname format")
        
        if not data.get('provider', '').strip():
            errors.append("Provider is required")
        
        # Optional fields validation
        if data.get('practitioner_name') and not SecurityValidator.validate_name(data['practitioner_name']):
            errors.append("Invalid practitioner name format")
        
        # Validate SKUs
        for i in range(1, 4):
            sku = data.get(f'item_sku_{i}', '').strip()
            qty = data.get(f'item_qty_{i}', '')
            
            if sku and not SecurityValidator.validate_sku(sku):
                errors.append(f"Invalid SKU format for item {i}")
            
            if sku and qty:
                try:
                    qty_int = int(qty)
                    if qty_int < 1 or qty_int > 1000:
                        errors.append(f"Quantity for item {i} must be between 1 and 1000")
                except ValueError:
                    errors.append(f"Invalid quantity for item {i}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_practitioner_data(data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate practitioner form data."""
        errors = []
        
        # Required fields
        if not data.get('first_name', '').strip():
            errors.append("First name is required")
        elif not SecurityValidator.validate_name(data['first_name']):
            errors.append("Invalid first name format")
        
        if not data.get('provider', '').strip():
            errors.append("Provider is required")
        
        # Optional fields validation
        if data.get('last_name') and not SecurityValidator.validate_name(data['last_name']):
            errors.append("Invalid last name format")
        
        if data.get('email') and not SecurityValidator.validate_email(data['email']):
            errors.append("Invalid email format")
        
        if data.get('phone') and not SecurityValidator.validate_phone(data['phone']):
            errors.append("Invalid phone format")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_stock_item_data(data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate stock item form data."""
        errors = []
        
        # Required fields
        if not data.get('name', '').strip():
            errors.append("Item name is required")
        elif len(data['name'].strip()) > 120:
            errors.append("Item name too long (max 120 characters)")
        
        if not data.get('provider', '').strip():
            errors.append("Provider is required")
        
        # Optional fields validation
        if data.get('code_type') and len(data['code_type']) > 20:
            errors.append("Code type too long (max 20 characters)")
        
        if data.get('current_stock'):
            try:
                stock = int(data['current_stock'])
                if stock < 0 or stock > 10000:
                    errors.append("Current stock must be between 0 and 10000")
            except ValueError:
                errors.append("Invalid current stock value")
        
        return len(errors) == 0, errors


class RateLimiter:
    """Simple rate limiting implementation."""
    
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, identifier: str, limit: int = 100, window: int = 3600) -> bool:
        """Check if request is within rate limit."""
        import time
        current_time = time.time()
        
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if current_time - req_time < window
        ]
        
        # Check limit
        if len(self.requests[identifier]) >= limit:
            return False
        
        # Add current request
        self.requests[identifier].append(current_time)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter()



