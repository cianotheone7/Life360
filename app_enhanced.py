"""
Enhanced Life360 Management System - Main Application Entry Point
This file integrates all the new modules and provides a production-ready application.
"""
import os
import logging
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_from_directory, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, and_
import msal
from urllib.parse import urlencode
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from openpyxl import Workbook
import base64, requests
import secrets
from dotenv import load_dotenv
from pathlib import Path as _P
from jinja2 import TemplateNotFound

# Import our new modules
from config import init_config, get_config
from security import SecurityValidator, InputValidator, rate_limiter
from error_handling import ErrorHandler, log_user_action, log_security_event
from api import create_api_blueprint
from migrations import run_migrations, get_migration_status
from monitoring import create_health_endpoints

# Load environment variables
load_dotenv(dotenv_path=_P(__file__).with_name('.env'))
load_dotenv(override=False)

# Initialize configuration
config = init_config()

# Create Flask application
app = Flask(__name__)

# Apply configuration
app.config.update(config.to_flask_config())

# Ensure correct scheme/host when behind Azure App Service proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'

# Initialize database
db = SQLAlchemy(app)

# Initialize error handling
ErrorHandler.init_app(app, config.logging.file_path)

# Initialize monitoring
create_health_endpoints(app, db)

# Register API blueprint
api_bp = create_api_blueprint(db)
app.register_blueprint(api_bp)

# ---- LIVE MODE SWITCH ----
DEMO_MODE = config.demo_mode

def _first_writable_dir(candidates):
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            testfile = os.path.join(d, ".write_test")
            with open(testfile, "w") as fh:
                fh.write("ok")
            os.remove(testfile)
            return d
        except Exception:
            continue
    return "/tmp"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.environ.get("HOME", "/home")

# Upload configuration
_upload_candidates = [
    os.path.join(BASE_DIR, "uploads"),
    os.path.join(HOME_DIR, "data", "uploads"),
    os.path.join(HOME_DIR, "uploads"),
    "/tmp/uploads",
]
UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", _first_writable_dir(_upload_candidates))

# =========================
# Database Models (Enhanced)
# =========================

class StockItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    received_date = db.Column(db.Date, nullable=True)
    code_type = db.Column(db.String(20), nullable=False, default="Kit")
    person_requested = db.Column(db.String(120), nullable=True)
    request_datetime = db.Column(db.DateTime, nullable=True)
    current_stock = db.Column(db.Integer, nullable=False, default=0)
    provider = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class StockUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(120), unique=True, nullable=False)
    batch_number = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="In Stock")
    item_id = db.Column(db.Integer, db.ForeignKey('stock_item.id'), nullable=False)
    item = db.relationship("StockItem", backref=db.backref("units", lazy="dynamic"))
    last_update = db.Column(db.DateTime, default=datetime.utcnow)

class OrderUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('stock_unit.id'), nullable=False)
    unit = db.relationship("StockUnit")
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(120), nullable=True)
    name = db.Column(db.String(120), nullable=True)
    surname = db.Column(db.String(120), nullable=True)
    practitioner_name = db.Column(db.String(120), nullable=True)
    ordered_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(40), nullable=False, default="Pending")
    notes = db.Column(db.Text, nullable=True)
    email_status = db.Column(db.String(60), nullable=True)
    sent_out = db.Column(db.Boolean, default=False)
    received_back = db.Column(db.Boolean, default=False)
    kit_registered = db.Column(db.Boolean, default=False)
    results_sent = db.Column(db.Boolean, default=False)
    paid = db.Column(db.Boolean, default=False)
    invoiced = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    sku = db.Column(db.String(120), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    provider = db.Column(db.String(120), nullable=True)
    assignee = db.Column(db.String(120), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="Open")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(120), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderCallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)
    when = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.Column(db.String(120), nullable=True)
    summary = db.Column(db.Text, nullable=False)
    outcome = db.Column(db.String(60), nullable=True)

class Practitioner(db.Model):
    __tablename__ = 'practitioners'  # Use the correct table name
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(80))
    title = db.Column(db.String(20))
    first_name = db.Column(db.String(120))
    last_name = db.Column(db.String(120))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(40))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PractitionerFlag(db.Model):
    __tablename__ = 'practitioner_flag'
    id = db.Column(db.Integer, primary_key=True)
    pid = db.Column(db.Integer, unique=True, nullable=False)
    training = db.Column(db.Boolean, default=False)
    website = db.Column(db.Boolean, default=False)
    whatsapp = db.Column(db.Boolean, default=False)
    engagebay = db.Column(db.Boolean, default=False)
    onboarded = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========================
# Enhanced Route Handlers
# =========================

@app.route("/")
def dashboard():
    """Enhanced dashboard with security logging."""
    user = session.get("user")
    if user:
        log_user_action(user.get('oid', 'unknown'), 'dashboard_access')
    
    # Get statistics with error handling
    try:
        total_prac = db.session.query(func.count(Practitioner.id)).scalar()
        onboarded = db.session.query(func.count(PractitionerFlag.id)).filter_by(onboarded=True).scalar()
        pending_prac = (total_prac or 0) - (onboarded or 0)

        total_orders = db.session.query(Order).count()
        completed_orders = db.session.query(Order).filter(Order.status.ilike("%completed%")).count()
        cancelled_orders = db.session.query(Order).filter(Order.status.ilike("%cancel%")).count()
        pending_orders = total_orders - completed_orders - cancelled_orders

        orders = []
        for o in db.session.query(Order).order_by(Order.created_at.desc()).limit(100).all():
            items = [{"sku": it.sku, "qty": it.qty} for it in o.items]
            orders.append({
                "id": o.id, "provider": o.provider, "name": o.name, "surname": o.surname,
                "status": o.status, "created_at": o.created_at.isoformat() if o.created_at else None,
                "completed_at": o.completed_at.isoformat() if o.completed_at else None,
                "items": items,
                "sent_out": o.sent_out, "received_back": o.received_back, "kit_registered": o.kit_registered,
                "results_sent": o.results_sent, "paid": o.paid, "invoiced": o.invoiced,
            })

        return render_template("dashboard.html", user=user,
                            total_prac=total_prac, onboarded=onboarded, pending_prac=pending_prac,
                            total_orders=total_orders, completed_orders=completed_orders, pending_orders=pending_orders,
                            orders=orders)
    except Exception as e:
        app.logger.error(f"Dashboard error: {e}")
        flash("Error loading dashboard data", "error")
        return render_template("dashboard.html", user=user,
                            total_prac=0, onboarded=0, pending_prac=0,
                            total_orders=0, completed_orders=0, pending_orders=0,
                            orders=[])

@app.route("/orders/new", methods=["POST"])
def create_order():
    """Enhanced order creation with validation."""
    try:
        # Validate input data
        data = {
            'name': request.form.get('name', '').strip(),
            'surname': request.form.get('surname', '').strip(),
            'provider': request.form.get('provider', '').strip(),
            'practitioner_name': request.form.get('practitioner_name', '').strip(),
            'notes': request.form.get('notes', '').strip(),
            'status': request.form.get('status', 'Pending'),
            'ordered_at': request.form.get('ordered_at', ''),
            'item_sku_1': request.form.get('item_sku_1', '').strip(),
            'item_qty_1': request.form.get('item_qty_1', ''),
            'item_sku_2': request.form.get('item_sku_2', '').strip(),
            'item_qty_2': request.form.get('item_qty_2', ''),
            'item_sku_3': request.form.get('item_sku_3', '').strip(),
            'item_qty_3': request.form.get('item_qty_3', ''),
        }
        
        # Validate using our security module
        is_valid, errors = InputValidator.validate_order_data(data)
        if not is_valid:
            for error in errors:
                flash(error, "error")
            return redirect(url_for('new_order_form'))
        
        # Create order with normalized provider
        provider = SecurityValidator.normalize_provider(data['provider'])
        ordered_at_str = data['ordered_at']
        try:
            ordered_at = datetime.fromisoformat(ordered_at_str) if ordered_at_str else datetime.utcnow()
        except Exception:
            ordered_at = datetime.utcnow()
        
        order = Order(
            provider=provider,
            name=data['name'],
            surname=data['surname'],
            practitioner_name=data['practitioner_name'] or None,
            notes=data['notes'] or None,
            ordered_at=ordered_at,
            status=data['status']
        )
        
        db.session.add(order)
        db.session.flush()

        # Add order items with validation
        for i in range(1, 4):
            sku = data.get(f'item_sku_{i}', '').strip()
            qty = data.get(f'item_qty_{i}', '')
            
            if sku and qty:
                if SecurityValidator.validate_sku(sku):
                    try:
                        qty_int = int(qty)
                        if 1 <= qty_int <= 1000:
                            db.session.add(OrderItem(order_id=order.id, sku=sku, qty=qty_int))
                    except ValueError:
                        pass
        
        db.session.commit()
        
        # Log user action
        user = session.get("user")
        if user:
            log_user_action(user.get('oid', 'unknown'), 'create_order', {'order_id': order.id})
        
        flash(f"Order #{order.id} created successfully.", "success")
        return redirect(url_for("orders"))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Order creation error: {e}")
        flash("Failed to create order. Please try again.", "error")
        return redirect(url_for('new_order_form'))

@app.route("/practitioners/new", methods=["POST"])
def practitioners_new():
    """Enhanced practitioner creation with validation."""
    try:
        # Validate input data
        data = {
            'first_name': request.form.get('first_name', '').strip(),
            'last_name': request.form.get('last_name', '').strip(),
            'provider': request.form.get('provider', '').strip(),
            'title': request.form.get('title', '').strip(),
            'email': request.form.get('email', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'notes': request.form.get('notes', '').strip(),
        }
        
        # Validate using our security module
        is_valid, errors = InputValidator.validate_practitioner_data(data)
        if not is_valid:
            for error in errors:
                flash(error, "error")
            return render_template("practitioner_new.html")
        
        # Create practitioner with normalized provider
        practitioner = Practitioner(
            provider=SecurityValidator.normalize_provider(data['provider']),
            title=data['title'] or None,
            first_name=data['first_name'],
            last_name=data['last_name'] or None,
            email=data['email'] or None,
            phone=data['phone'] or None,
            notes=SecurityValidator.sanitize_html(data['notes']) or None,
        )
        
        db.session.add(practitioner)
        db.session.commit()
        
        # Log user action
        user = session.get("user")
        if user:
            log_user_action(user.get('oid', 'unknown'), 'create_practitioner', {'practitioner_id': practitioner.id})
        
        flash("Practitioner added successfully.", "success")
        return redirect(url_for("practitioners"))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Practitioner creation error: {e}")
        flash("Failed to add practitioner.", "error")
        return render_template("practitioner_new.html")

# =========================
# Enhanced Security Routes
# =========================

@app.route("/login")
def login():
    """Enhanced login with security logging."""
    client_id = config.azure.client_id
    if not client_id:
        app.logger.error("AZURE_CLIENT_ID missing")
        flash("Authentication not configured", "error")
        return redirect(url_for("dashboard"))
    
    # Log login attempt
    log_security_event('login_attempt', {'ip': request.remote_addr})
    
    session["auth_in_progress"] = True
    session["state"] = secrets.token_urlsafe(16)
    
    # Build auth URL using MSAL
    app_msal = msal.ConfidentialClientApplication(
        client_id, authority=config.azure.authority,
        client_credential=config.azure.client_secret
    )
    
    auth_url = app_msal.get_authorization_request_url(
        [config.azure.scope],
        state=session["state"],
        redirect_uri=url_for("authorized", _external=True)
    )
    
    return redirect(auth_url)

@app.route("/logout")
def logout():
    """Enhanced logout with security logging."""
    user = session.get("user")
    if user:
        log_user_action(user.get('oid', 'unknown'), 'logout')
    
    session.clear()
    params = {"post_logout_redirect_uri": url_for("dashboard", _external=True)}
    return redirect(f"{config.azure.authority}/oauth2/v2.0/logout?{urlencode(params)}")

# =========================
# Helper Functions
# =========================

def in_stock_q():
    """Query for getting accurate stock counts from StockUnit table."""
    return (
        db.session.query(
            StockItem.id.label("item_id"),
            StockItem.name,
            StockItem.provider,
            func.count(StockUnit.id).label("in_stock"),
        )
        .join(
            StockUnit,
            StockUnit.item_id == StockItem.id
        )
        .filter(StockUnit.status == "In Stock")
        .group_by(StockItem.id, StockItem.name, StockItem.provider)
    )

def normalize_provider(provider_name):
    """Normalize provider name to match configured providers."""
    if not provider_name:
        return None
    
    # Get the list of valid providers from config
    valid_providers = config.get_provider_list()
    
    # Try exact match first
    if provider_name in valid_providers:
        return provider_name
    
    # Try case-insensitive match
    for valid_provider in valid_providers:
        if provider_name.lower() == valid_provider.lower():
            return valid_provider
    
    # Try partial match
    for valid_provider in valid_providers:
        if provider_name.lower() in valid_provider.lower() or valid_provider.lower() in provider_name.lower():
            return valid_provider
    
    return provider_name

# =========================
# AI Functionality
# =========================

@app.route("/api/ask_ai", methods=["POST"])
def ask_ai():
    """Intent-aware AI endpoint, with DB-backed answers and optional OpenRouter fallback."""
    data = request.get_json(force=True, silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    prompt = raw_prompt.lower()
    
    # Debug logging
    app.logger.info(f"AI Query: '{raw_prompt}' -> '{prompt}'")
    app.logger.info(f"Query contains 'practitioners': {'practitioners' in prompt}")
    app.logger.info(f"Query contains 'practitioner': {'practitioner' in prompt}")
    app.logger.info(f"Query contains 'orders': {'orders' in prompt}")
    
    # Remove debug code - all queries will go through OpenRouter

    def wants_json():
        return " as json" in prompt or prompt.strip().endswith("json") or "json please" in prompt

    def parse_days(text, default=30):
        import re
        m = re.search(r'(\d+)\s*(day|days|d)\b', text)
        return int(m.group(1)) if m else default

    def parse_threshold(text, default=2):
        import re
        m = re.search(r'(?:<=|under)\s*(\d+)', text)
        return int(m.group(1)) if m else default

    def parse_order_id(text):
        import re
        m = re.search(r'(?:order\s*#?|id\s*#?)(\d+)', text)
        return int(m.group(1)) if m else None

    total = db.session.query(Order).count()
    completed = db.session.query(Order).filter(Order.status.ilike("%completed%")).count()
    cancelled = db.session.query(Order).filter(Order.status.ilike("%cancel%")).count()
    pending = total - completed - cancelled

    # All queries will go through OpenRouter with comprehensive context

    # Build comprehensive context for OpenRouter
    try:
        app.logger.info("Building comprehensive context...")
        
        # Stock data
        app.logger.info("Querying stock data...")
        stock_counts = in_stock_q().order_by('in_stock').limit(50).all()
        app.logger.info(f"Found {len(stock_counts)} stock items")
        
        low_stock = [{"name": item.name, "qty": int(item.in_stock), "provider": item.provider} for item in stock_counts if int(item.in_stock) <= 2]
        stock_providers = ", ".join(set(item.provider for item in stock_counts if item.provider))
        
        # Get detailed stock information
        stock_items = []
        for item in stock_counts[:20]:  # Top 20 stock items
            stock_items.append(f"{item.name}({item.in_stock})")
        
        # Practitioner data
        app.logger.info("Querying practitioner data...")
        total_practitioners = db.session.query(Practitioner).count()
        onboarded_practitioners = db.session.query(PractitionerFlag).filter_by(onboarded=True).count()
        pending_practitioners = total_practitioners - onboarded_practitioners
        app.logger.info(f"Found {total_practitioners} practitioners, {onboarded_practitioners} onboarded")
        
        # Get practitioner provider breakdown
        practitioner_providers = db.session.query(
            Practitioner.provider, 
            func.count(Practitioner.id).label('count')
        ).group_by(Practitioner.provider).all()
        practitioner_provider_list = [f"{p.provider}({p.count})" for p in practitioner_providers]
        
        # Get sample practitioners
        sample_practitioners = db.session.query(Practitioner).limit(10).all()
        practitioner_names = [f"{p.first_name} {p.last_name}({p.provider})" for p in sample_practitioners]
        
        # Order status breakdown
        order_statuses = db.session.query(
            Order.status,
            func.count(Order.id).label('count')
        ).group_by(Order.status).all()
        order_status_list = [f"{s.status}({s.count})" for s in order_statuses]
        
        # Build comprehensive context
        context = f"""
LIFE360 MANAGEMENT SYSTEM DATA:

ORDERS:
- Total: {total} orders
- Completed: {completed} orders  
- Pending: {pending} orders
- Cancelled: {cancelled} orders
- Status breakdown: {', '.join(order_status_list)}

STOCK INVENTORY:
- Total stock items: {len(stock_counts)}
- Stock providers: {stock_providers}
- Low stock items (≤2): {low_stock}
- Top stock items: {', '.join(stock_items[:10])}

PRACTITIONERS:
- Total: {total_practitioners} practitioners
- Onboarded: {onboarded_practitioners} practitioners
- Pending: {pending_practitioners} practitioners
- Provider breakdown: {', '.join(practitioner_provider_list)}
- Sample practitioners: {', '.join(practitioner_names[:5])}

Answer questions about orders, stock, and practitioners using this data. Be specific and accurate with numbers.
        """.strip()
        
        app.logger.info("Context built successfully")
        
    except Exception as e:
        app.logger.error(f"Error building context: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        context = f"Orders: {total} total, {completed} completed, {pending} pending. Error loading detailed data: {e}"

    # All queries go through OpenRouter with comprehensive context
    if config.openrouter.api_key:
        app.logger.info(f"Sending query to OpenRouter: '{raw_prompt}'")
        app.logger.info(f"Context length: {len(context)} characters")
        try:
            import requests
            headers = {
                'Authorization': f'Bearer {config.openrouter.api_key}',
                'Content-Type': 'application/json',
                'X-Title': config.openrouter.title or 'Life360 Dashboard Ask AI',
                'X-Site-URL': config.openrouter.site_url or (request.host_url.rstrip('/') if request else ''),
            }
            payload = {
                'model': config.openrouter.model,
                'messages': [
                    {'role': 'system', 'content': 'You are a Life360 management system assistant. Use the provided data to answer questions about orders, stock inventory, and practitioners. Be accurate with numbers and provide specific details when asked.'},
                    {'role': 'user', 'content': f"{context}\n\nQuestion: {raw_prompt}"}
                ]
            }
            resp = requests.post(config.openrouter.url, headers=headers, json=payload, timeout=60)
            app.logger.info(f"OpenRouter response status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                if 'choices' in data and len(data['choices']) > 0:
                    answer = data['choices'][0]['message']['content']
                    app.logger.info(f"OpenRouter answer: {answer[:100]}...")
                    return {"ok": True, "answer": answer}
                else:
                    app.logger.error(f"No choices in OpenRouter response: {data}")
            else:
                app.logger.error(f"OpenRouter call failed: {resp.status_code} - {resp.text}")
                
        except Exception as e:
            app.logger.error(f"OpenRouter call failed: {e}")
            import traceback
            app.logger.error(traceback.format_exc())
    else:
        app.logger.warning("No OpenRouter API key configured")

    # Fallback if OpenRouter is not available
    return {"ok": True, "answer": f"Orders: {total} total, {completed} completed, {pending} pending. Please configure OpenRouter API key for detailed responses."}

# =========================
# Application Initialization
# =========================

def _ensure_tables():
    """Create database tables and run migrations."""
    try:
        db.create_all()
        # Run migrations
        run_migrations(db)
        app.logger.info("Database tables created and migrations applied")
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")

@app.before_request
def _require_login():
    """Enhanced login requirement with rate limiting."""
    # Allow these paths without auth
    allow_prefixes = ("/static/", "/favicon.ico", "/health", "/metrics", "/ready", "/live")
    allow_exact = {"/login", "/logout", "/auth/diagnostics", "/getAToken"}
    
    p = request.path or "/"
    if p.startswith(allow_prefixes) or p in allow_exact:
        return None
    
    if session.get("auth_in_progress"):
        return None
    
    # Check rate limiting
    if config.security.rate_limit_enabled:
        client_id = request.remote_addr
        if not rate_limiter.is_allowed(client_id, limit=100, window=3600):
            log_security_event('rate_limit_exceeded', {'ip': client_id})
            return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # Check authentication
    if not session.get("user") or not session.get("ms_expires_at") or int(time.time()) >= int(session.get("ms_expires_at")) - 60:
        session.clear()
        return redirect(url_for("login"))
    
    return None

# =========================
# Startup and Configuration
# =========================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=config.logging.format,
        handlers=[
            logging.FileHandler(config.logging.file_path) if config.logging.file_path else logging.StreamHandler(),
            logging.StreamHandler()
        ]
    )
    
    # Initialize database
    with app.app_context():
        _ensure_tables()
    
    # Log startup
    app.logger.info(f"Starting Life360 Management System v1.0.0")
    app.logger.info(f"Environment: {config.environment}")
    app.logger.info(f"Debug mode: {config.debug}")
    app.logger.info(f"Database: {config.database.url}")
    
    # Start application
    app.run(
        host=config.host,
        port=config.port,
        debug=config.debug
    )
