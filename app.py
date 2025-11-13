import os, json, time, uuid, re, logging
from datetime import datetime, date, timedelta, timezone
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_from_directory, send_file, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, and_, or_
import msal
from urllib.parse import urlencode
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from openpyxl import Workbook
import base64
import requests
import secrets
from dotenv import load_dotenv
from pathlib import Path as _P
from jinja2 import TemplateNotFound

# Load .env placed next to this file, regardless of CWD
load_dotenv(dotenv_path=_P(__file__).with_name('.env'))
# Also load from CWD if present (won't override existing)
load_dotenv(override=False)

# --------------------------------------------------------------------------------------
# App + robust writable paths (works on Azure "run from package" and local dev)
# --------------------------------------------------------------------------------------
app = Flask(__name__)
# Ensure correct scheme/host when behind Azure App Service proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'

# ---- LIVE MODE SWITCH ----
DEMO_MODE = os.environ.get("DEMO_MODE", "0").lower() in ("1", "true", "yes", "on")

def _first_writable_dir(candidates):
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            # write test
            testfile = os.path.join(d, ".write_test")
            with open(testfile, "w") as fh:
                fh.write("ok")
            os.remove(testfile)
            return d
        except Exception:
            continue
    # last resort
    return "/tmp"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.environ.get("HOME", "/home")

# Uploads: prefer app/uploads when writable, else /home/data/uploads, else /tmp/uploads
_upload_candidates = [
    os.path.join(BASE_DIR, "uploads"),
    os.path.join(HOME_DIR, "data", "uploads"),
    os.path.join(HOME_DIR, "uploads"),
    "/tmp/uploads",
]
UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", _first_writable_dir(_upload_candidates))
ALLOWED_EXT = {"pdf","doc","docx","xls","xlsx","csv","png","jpg","jpeg","txt","ppt","pptx"}

# Secret key
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me")

# Database: respect DATABASE_URL, otherwise choose a writable place for life360.db
def _sqlite_uri_for(file_path: str) -> str:
    # absolute path requires 4 slashes
    return "sqlite:///" + (file_path if not os.path.isabs(file_path) else "/" + file_path.lstrip("/"))

def _choose_sqlite_db_path():
    # If repo dir is read-only on Azure (WEBSITE_RUN_FROM_PACKAGE), fall back to /home/data or /tmp
    candidates = [
        os.path.join(BASE_DIR, "life360.db"),
        os.path.join(HOME_DIR, "data", "life360.db"),
        os.path.join(HOME_DIR, "life360.db"),
        "/tmp/life360.db",
    ]
    d = _first_writable_dir(list({os.path.dirname(c) for c in candidates}))
    return os.path.join(d, "life360.db")

if os.environ.get("DATABASE_URL"):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    print(f"Using DATABASE_URL from environment")
else:
    # Fall back to SQLite for local development
    sqlite_path = _choose_sqlite_db_path()
    app.config["SQLALCHEMY_DATABASE_URI"] = _sqlite_uri_for(sqlite_path)
    print(f"No DATABASE_URL set, using SQLite at: {sqlite_path}")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# PostgreSQL-specific connection pool settings for Azure
if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,  # Recycle connections every 30 min
        "pool_pre_ping": True,  # Verify connections before using
        "connect_args": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000"  # 30 second query timeout
        }
    }

db = SQLAlchemy(app)

# =========================
# Provider rename map (canonicalization)
# =========================
RENAME_MAP = {
    "Umvuzo Fedhealth": "Intelligene Fedhealth",
    "Umvuzo Intelligene": "Intelligene Umvuzo",  # legacy
}
REVERSE_MAP = {}
for _old, _new in RENAME_MAP.items():
    REVERSE_MAP.setdefault(_new, set()).add(_old)

def normalize_provider(name: str | None) -> str | None:
    if not name:
        return name
    return RENAME_MAP.get(name, name)

# --- Jinja filter: split (for environments that lack it) ---
@app.template_filter("split")
def jinja_split(value, sep="|"):
    if value is None:
        return []
    return str(value).split(sep)

# --- Demo timer sample (not used by main orders view) ---
orders_demo = [
    {"id": 1, "name": "Medicine A", "ordered_at": "2025-08-30 10:00", "assigned": 1, "required": 2, "created_at": datetime.now(timezone.utc)},
    {"id": 2, "name": "Medicine B", "ordered_at": "2025-08-29 08:00", "assigned": 0, "required": 1, "created_at": datetime.now(timezone.utc) - timedelta(hours=25)},
    {"id": 3, "name": "Medicine C", "ordered_at": "2025-08-30 15:00", "assigned": 2, "required": 2, "created_at": datetime.now(timezone.utc) - timedelta(hours=5)},
]

def time_left(obj):
    """Return remaining time info using UTC-aware datetimes.
    Accepts either a dict (expects 'created_at' and optional 'sla_hours')
    or an object with attribute 'created_at'.
    """
    def ensure_utc(dt):
        if dt is None:
            return None
        if isinstance(dt, str):
            try:
                dtp = datetime.fromisoformat(dt)
                if dtp.tzinfo is None:
                    dtp = dtp.replace(tzinfo=timezone.utc)
                else:
                    dtp = dtp.astimezone(timezone.utc)
                return dtp
            except Exception:
                return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    if isinstance(obj, dict):
        created = ensure_utc(obj.get("created_at"))
        sla_hours = obj.get("sla_hours", 24)
    else:
        created = ensure_utc(getattr(obj, "created_at", None))
        sla_hours = 24

    if not created:
        return {"remaining_hours": None, "overdue": False}

    expiry_time = created + timedelta(hours=sla_hours)
    now_utc = datetime.now(timezone.utc)
    remaining = expiry_time - now_utc
    remaining_hours = round(remaining.total_seconds() / 3600.0, 1)
    return {"remaining_hours": remaining_hours, "overdue": remaining_hours < 0}

# --- Robust secret loader (env -> .env -> secret.txt -> NO hardcoded fallback) ---
def _load_client_secret():
    # 1) Environment variable (Azure App Settings)
    v = os.environ.get("AZURE_CLIENT_SECRET")
    if v:
        return v, "env"
    # 2) .env file next to app.py (local dev / optional)
    try:
        from dotenv import dotenv_values as _dotenv_values
        _envp = _P(__file__).with_name(".env")
        if _envp.exists():
            cfg = _dotenv_values(_envp)
            if cfg.get("AZURE_CLIENT_SECRET"):
                return cfg.get("AZURE_CLIENT_SECRET"), ".env"
    except Exception:
        pass
    # 3) secret.txt file next to app.py (emergency fallback for Azure)
    _secretp = _P(__file__).with_name("secret.txt")
    if _secretp.exists():
        try:
            val = _secretp.read_text().strip()
            if val:
                return val, "secret.txt"
        except Exception:
            pass
    # 4) Last resort: return empty, so auth fails fast instead of using a hardcoded secret
    return "", "missing"

# Azure (prefer ENV; avoid random defaults)
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "common")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
CLIENT_SECRET, _CLIENT_SECRET_SRC = _load_client_secret()
AUTHORITY = os.environ.get("AZURE_AUTHORITY", f"https://login.microsoftonline.com/{TENANT_ID}")
REDIRECT_PATH = os.environ.get("AZURE_REDIRECT_PATH", "/getAToken")
SCOPE = os.environ.get("AZURE_SCOPE", "User.Read")

# Canonical provider list (include Reboot for new order form)
PROVIDERS = [
    "Geneway", "Optiway", "Enbiosis", "Intelligene", "Healthy Me",
    "Intelligene Fedhealth", "Geko", "Reboot", "Gifts & Banners",
]

# ---------------- Models ----------------
class StockItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    received_date = db.Column(db.Date, nullable=True)
    # These remain for backward compatibility but are not shown in UI:
    code_type = db.Column(db.String(20), nullable=False, default="Kit")
    person_requested = db.Column(db.String(120), nullable=True)
    request_datetime = db.Column(db.DateTime, nullable=True)
    current_stock = db.Column(db.Integer, nullable=False, default=0)
    provider = db.Column(db.String(120), nullable=True)

class StockUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(120), nullable=False)  # Removed unique=True to allow duplicate barcodes
    batch_number = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="In Stock")
    item_id = db.Column(db.Integer, db.ForeignKey('stock_item.id'), nullable=False)
    item = db.relationship("StockItem", backref=db.backref("units", lazy="dynamic"))
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Promotional use tracking
    promotional_use = db.Column(db.Boolean, default=False)  # Signed out for promotional use
    signed_out_by = db.Column(db.String(120), nullable=True)  # Staff member name
    signed_out_date = db.Column(db.DateTime, nullable=True)  # When it was signed out
    promotional_notes = db.Column(db.Text, nullable=True)  # Notes about promotional use
    
    # Return tracking
    returned = db.Column(db.Boolean, default=False)  # Has been returned
    returned_by = db.Column(db.String(120), nullable=True)  # Who returned it
    returned_date = db.Column(db.DateTime, nullable=True)  # When it was returned
    return_reason = db.Column(db.Text, nullable=True)  # Why it was returned (e.g., "Not sold at event")

class OrderUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)  # link to in-memory order id
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
    opt_in_status = db.Column(db.String(20), nullable=True, default=None)  # "Opted In", "Opted Out", or None for "Pending"
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
    
    # WooCommerce integration fields
    woocommerce_id = db.Column(db.Integer, nullable=True, unique=True)  # WooCommerce order ID
    customer_name = db.Column(db.String(240), nullable=True)  # Full customer name
    customer_email = db.Column(db.String(200), nullable=True)  # Customer email
    customer_phone = db.Column(db.String(40), nullable=True)  # Customer phone
    address = db.Column(db.Text, nullable=True)  # Full address
    items_description = db.Column(db.Text, nullable=True)  # Items ordered
    total_amount = db.Column(db.Float, nullable=True)  # Order total
    order_date = db.Column(db.DateTime, nullable=True)  # WooCommerce order date
    payment_method = db.Column(db.String(100), nullable=True)  # Payment method
    
    # Fillout integration fields
    fillout_submission_id = db.Column(db.String(100), nullable=True, unique=True)  # Fillout submission ID
    
    # Raw API data storage for detailed view
    raw_api_data = db.Column(db.Text, nullable=True)  # Store complete API response as JSON
    
    # Payment tracking fields
    pop_received = db.Column(db.Boolean, default=False)  # Proof of Payment received
    payment_received = db.Column(db.Boolean, default=False)  # Payment received (required before lab submission)
    awaiting_payment = db.Column(db.Boolean, default=False)  # Awaiting payment
    payment_notes = db.Column(db.Text, nullable=True)  # Payment-related notes
    payment_date = db.Column(db.DateTime, nullable=True)  # Date payment was received
    
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
    status = db.Column(db.String(40), nullable=False, default="Open")  # Open, In Progress, Done
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(120), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)  # unique identifier for the file
    file_data = db.Column(db.LargeBinary, nullable=True)  # Store file content in database (nullable for old records)
    file_size = db.Column(db.Integer, nullable=True)  # Size in bytes (nullable for old records)
    content_type = db.Column(db.String(100), nullable=True)  # MIME type
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class SalesOrderPDF(db.Model):
    """Model for storing Sales Order PDFs in database"""
    __tablename__ = 'sales_order_pdf'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)  # Store PDF as binary data
    file_size = db.Column(db.Integer, nullable=False)  # Size in bytes
    uploaded_by = db.Column(db.String(120), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    content_type = db.Column(db.String(100), default='application/pdf')
    
    def get_file_size_formatted(self):
        """Return formatted file size"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

class OrderCallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)
    when = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.Column(db.String(120), nullable=True)
    summary = db.Column(db.Text, nullable=False)
    outcome = db.Column(db.String(60), nullable=True)


class Practitioner(db.Model):
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
    pid = db.Column(db.Integer, unique=True, nullable=False)  # matches PRACTITIONERS[] 'id'
    training  = db.Column(db.Boolean, default=False)
    website   = db.Column(db.Boolean, default=False)
    whatsapp  = db.Column(db.Boolean, default=False)
    engagebay = db.Column(db.Boolean, default=False)
    onboarded = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class CourierBooking(db.Model):
    __tablename__ = 'courier_booking'
    id = db.Column(db.Integer, primary_key=True)
    practitioner_id = db.Column(db.Integer, db.ForeignKey('practitioner.id'), nullable=False)
    shiplogic_booking_id = db.Column(db.String(100), unique=True, nullable=False)
    tracking_number = db.Column(db.String(100), unique=True, nullable=False)
    
    # Provider details
    provider = db.Column(db.String(50), nullable=False, default='courier_guy_geneway')  # courier_guy_geneway, courier_guy_healthy_me, courier_guy_intelligence, mds_geneway
    
    # Booking details
    pickup_address = db.Column(db.Text, nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    recipient_name = db.Column(db.String(200), nullable=False)
    recipient_phone = db.Column(db.String(50), nullable=False)
    package_description = db.Column(db.Text, nullable=True)
    package_weight = db.Column(db.Float, default=1.0)
    package_value = db.Column(db.Float, default=0.0)
    special_instructions = db.Column(db.Text, nullable=True)
    
    # Service details
    service_type = db.Column(db.String(10), nullable=True)  # LOF, LSF, LOX, LSE, SDX
    service_cost = db.Column(db.Float, nullable=True)
    
    # Waybill details
    waybill_url = db.Column(db.String(500), nullable=True)
    waybill_data = db.Column(db.Text, nullable=True)  # JSON data for waybill
    waybill_generated = db.Column(db.Boolean, default=False)
    
    # Status and tracking
    status = db.Column(db.String(50), default='pending')  # pending, confirmed, picked_up, in_transit, delivered, cancelled
    estimated_delivery = db.Column(db.DateTime, nullable=True)
    actual_delivery = db.Column(db.DateTime, nullable=True)
    cost = db.Column(db.Float, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    practitioner = db.relationship('Practitioner', backref='courier_bookings')

class CourierUpdate(db.Model):
    __tablename__ = 'courier_update'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('courier_booking.id'), nullable=False)
    
    # Update details
    status = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    booking = db.relationship('CourierBooking', backref='updates')

class PromotionalItem(db.Model):
    """Model for tracking promotional items, gifts, banners, and gazebos"""
    __tablename__ = 'promotional_item'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Item name
    category = db.Column(db.String(50), nullable=False)  # Gift, Banner, Gazebo, etc.
    description = db.Column(db.Text, nullable=True)  # Item description
    quantity = db.Column(db.Integer, nullable=False, default=1)  # Total quantity
    available_quantity = db.Column(db.Integer, nullable=False, default=1)  # Available quantity
    
    # Tracking fields
    location = db.Column(db.String(200), nullable=True)  # Where it's stored
    condition = db.Column(db.String(50), nullable=True)  # New, Good, Fair, Poor
    purchase_date = db.Column(db.Date, nullable=True)  # When it was purchased
    cost = db.Column(db.Float, nullable=True)  # Purchase cost
    
    # Signed out tracking
    signed_out = db.Column(db.Boolean, default=False)  # Currently signed out
    signed_out_by = db.Column(db.String(120), nullable=True)  # Staff member name
    signed_out_date = db.Column(db.DateTime, nullable=True)  # When signed out
    expected_return_date = db.Column(db.Date, nullable=True)  # Expected return date
    sign_out_notes = db.Column(db.Text, nullable=True)  # Purpose/notes
    
    # Return tracking
    last_returned_date = db.Column(db.DateTime, nullable=True)  # Last return date
    last_returned_by = db.Column(db.String(120), nullable=True)  # Who returned it last
    return_notes = db.Column(db.Text, nullable=True)  # Return notes
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)  # General notes

# ---------------- Dummy Data ----------------
PRACTITIONERS = []
ORDERS = []


# ---------- Helpers ----------

def in_stock_q():
    """Query for getting accurate stock counts from StockUnit table."""
    return (
        db.session.query(
            StockItem.id.label("item_id"),
            StockItem.name,
            StockItem.provider,
            func.count(StockUnit.id).label("in_stock"),
        )
        .outerjoin(
            StockUnit,
            and_(StockUnit.item_id == StockItem.id, StockUnit.status == "In Stock")
        )
        .group_by(StockItem.id, StockItem.name, StockItem.provider)
    )

def overlay_practitioner_flags():
    """Overlay persisted flags from DB onto the in-memory PRACTITIONERS list."""
    try:
        flags = {f.pid: f for f in PractitionerFlag.query.all()}
        for p in PRACTITIONERS:
            f = flags.get(p.get("id"))
            if f:
                p["training"]  = bool(getattr(f, "training", False))
                p["website"]   = bool(getattr(f, "website", False))
                p["whatsapp"]  = bool(getattr(f, "whatsapp", False))
                p["engagebay"] = bool(getattr(f, "engagebay", False))
                p["onboarded"] = bool(getattr(f, "onboarded", False))
    except Exception as e:
        app.logger.warning(f"PractitionerFlag overlay skipped: {e}")

def _bucket_practitioners(rows):
    buckets = {'pending': {}, 'completed': {}}
    for p in rows:
        b = 'completed' if p.get('onboarded') else 'pending'
        prov = p.get('provider') or '-'
        buckets[b].setdefault(prov, []).append(p)
    return buckets

def listify_interests(v):
    if not v:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).replace("\r", "\n")
    for ch in ["•", ";", "|", ","]:
        s = s.replace(ch, "\n")
    parts = [p.strip(" -\t") for p in s.split("\n")]
    return [p for p in parts if p]

def parse_date(v):
    if not v: return None
    try:
        return datetime.fromisoformat(v).date() if "T" in v else date.fromisoformat(v)
    except: return None

def parse_dt(v):
    if not v: return None
    try:
        return datetime.fromisoformat(v)
    except: return None

def batch_summary_for_item(item_id: int) -> str:
    """Return a compact Batch # summary for an item: single code or 'Mixed (N)'."""
    vals = [r[0] for r in db.session.query(StockUnit.batch_number)
            .filter(StockUnit.item_id == item_id).distinct().all()]
    vals = [v for v in vals if v]  # drop None/empty
    if not vals:
        return "-"
    if len(vals) == 1:
        return vals[0]
    return f"Mixed ({len(vals)})"


def seed_demo_if_empty():
    """Populate demo data; normalize providers to canonical names."""
    global PRACTITIONERS, ORDERS
    if not PRACTITIONERS:
        PRACTITIONERS = [
            {"id": 1, "provider": "Geneway", "title": "Ms", "first_name": "Thandi", "last_name": "Mkhize",
             "name": "Thandi", "surname": "Mkhize", "signed_up": "2025-08-20",
             "email": "thandi@example.com", "phone": "+27821234567",
             "occupation": "Dietitian", "city": "Cape Town", "province": "Western Cape", "postal_code": "8001",
             "registered_with_board": True,
             "interests": ["Genetic Screening", "Nutrigenomics"],
             "notes": "Cape Town clinic.",
             "onboarded": True, "training": True, "website": True, "whatsapp": True, "engagebay": True},
            {"id": 2, "provider": "Optiway", "title": "Mr", "first_name": "Sipho", "last_name": "Dlamini",
             "name": "Sipho", "surname": "Dlamini", "signed_up": "2025-08-22",
             "email": "sipho@example.com", "phone": "+27842223344",
             "occupation": "Health Coach", "city": "Pretoria", "province": "Gauteng", "postal_code": "0181",
             "registered_with_board": False,
             "interests": "Preventative Health, Microbiome",
             "notes": "Focus on microbiome kits.",
             "onboarded": False, "training": False, "website": False, "whatsapp": False, "engagebay": False},
        ]
        for p in PRACTITIONERS:
            p["provider"] = normalize_provider(p.get("provider"))

def migrate_orders_to_db():
    global ORDERS
    """One-time migration: copy in-memory demo ORDERS into DB if DB has no orders yet."""
    try:
        if db.session.query(Order).count() == 0 and ORDERS:
            for o in ORDERS:
                order = Order(
                    id=o.get("id"),
                    provider=normalize_provider(o.get("provider")),
                    name=o.get("name"),
                    surname=o.get("surname"),
                    practitioner_name=o.get("practitioner_name"),
                    ordered_at=datetime.fromisoformat(o.get("ordered_at")) if o.get("ordered_at") else datetime.now(timezone.utc),
                    status=o.get("status") or "Pending",
                    notes=o.get("notes"),
                    email_status=o.get("email_status"),
                    sent_out=bool(o.get("sent_out")),
                    received_back=bool(o.get("received_back")),
                    kit_registered=bool(o.get("kit_registered")),
                    results_sent=bool(o.get("results_sent")),
                    paid=bool(o.get("paid")),
                    invoiced=bool(o.get("invoiced")),
                    created_at=o.get("created_at") or datetime.now(timezone.utc),
                    completed_at=o.get("completed_at") if isinstance(o.get("completed_at"), datetime) else None,
                )
                db.session.add(order)
                for it in (o.get("items") or []):
                    db.session.add(OrderItem(order=order, sku=it.get("sku") or "SKU", qty=int(it.get("qty") or 1)))
            db.session.commit()
    except Exception as e:
        print("migrate_orders_to_db error:", e)

    if not ORDERS:
        ORDERS = [
            {"id": 101, "provider": "Geneway", "name": "Thandi", "surname": "Mkhize", "ordered_at": "2025-08-27T09:30:00",
             "items": [{"sku":"KIT-GEN-01","qty":3}], "status":"Pending", "notes":"Demo order.",
             "email_status":"ok", "sent_out": False, "received_back": False, "kit_registered": False,
             "results_sent": False, "paid": False, "invoiced": False, "practitioner_name": ""},
        ]
        for o in ORDERS:
            o["provider"] = normalize_provider(o.get("provider"))

def bucket_order(o):
    return 'completed' if all([o.get('received_back'), o.get('kit_registered'), o.get('results_sent'), o.get('paid'), o.get('invoiced')]) or o.get('status') == 'Completed' else 'pending'

# ---------------- Health + Ping ----------------

@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@app.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@app.get("/_ping")
def _ping():
    return {"ok": True, "service": "life360", "version": "1.0"}, 200

# ======== MyMobileAPI / SMS ========
# Load credentials from environment (do NOT hardcode secrets)
MYMOBILEAPI_USERNAME = os.environ.get("MYMOBILEAPI_USERNAME")
MYMOBILEAPI_PASSWORD = os.environ.get("MYMOBILEAPI_PASSWORD")
MYMOBILEAPI_URL = os.environ.get("MYMOBILEAPI_URL", "https://rest.mymobileapi.com/v3/BulkMessages")

def _ensure_tables():
    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f"db.create_all failed: {e}")

@app.route("/sms/send", methods=["POST"])
def sms_send():
    """Send an SMS via MyMobileAPI BulkMessages.
    Expected JSON: {"destination": "+27...", "message": "text", "testMode": false}
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        dest = (data.get("destination") or "").strip()
        msg  = (data.get("message") or "").strip()
        test_mode = bool(data.get("testMode", False))

        if not dest or not msg:
            return jsonify({"ok": False, "error": "Missing destination or message"}), 400

        if not (MYMOBILEAPI_USERNAME and MYMOBILEAPI_PASSWORD):
            return jsonify({"ok": False, "error": "SMS gateway not configured"}), 503

        auth_raw = f"{MYMOBILEAPI_USERNAME}:{MYMOBILEAPI_PASSWORD}".encode("utf-8")
        auth_hdr = "Basic " + base64.b64encode(auth_raw).decode("ascii")

        payload = {
            "sendOptions": {"testMode": test_mode},
            "messages": [
                {"destination": dest, "content": msg}
            ]
        }

        headers = {
            "Authorization": auth_hdr,
            "accept": "application/json",
            "content-type": "application/json",
        }

        try:
            resp = requests.post(MYMOBILEAPI_URL, json=payload, headers=headers, timeout=15)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            if resp.status_code == 200:
                return jsonify({"ok": True, "status": resp.status_code, "response": body})
            else:
                return jsonify({"ok": False, "status": resp.status_code, "response": body}), resp.status_code
        except requests.RequestException as e:
            return jsonify({"ok": False, "error": str(e)}), 502

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------- Dashboard ----------------

@app.route("/")
def dashboard():
    user = session.get("user")
    if DEMO_MODE:
        seed_demo_if_empty()
        migrate_orders_to_db()
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

@app.route("/practitioners")
def practitioners():
    user = session.get("user")
    filter_param = request.args.get('filter')  # Get filter parameter from URL
    
    # For DEMO mode: if DB empty, optionally seed from in-memory demo list
    created_demo = 0
    try:
        count = Practitioner.query.count()
    except Exception:
        count = 0
    if DEMO_MODE and count == 0:
        try:
            seed_demo_if_empty()
            # Copy demo PRACTITIONERS into DB once
            for p in PRACTITIONERS:
                obj = Practitioner(
                    provider=normalize_provider(p.get("provider")),
                    title=p.get("title"),
                    first_name=p.get("first_name") or p.get("name"),
                    last_name=p.get("last_name") or p.get("surname"),
                    email=p.get("email"),
                    phone=p.get("phone") or p.get("phone_e164"),
                    notes=p.get("notes"),
                )
                db.session.add(obj)
                created_demo += 1
            if created_demo:
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"DEMO mode practitioner seed to DB failed: {e}")
    # Query DB with optimized queries
    try:
        # Use JOIN to get practitioners and flags in one query for better performance
        practitioners_with_flags = db.session.query(
            Practitioner,
            PractitionerFlag
        ).outerjoin(
            PractitionerFlag, Practitioner.id == PractitionerFlag.pid
        ).order_by(
            Practitioner.provider, Practitioner.last_name, Practitioner.first_name
        ).all()
        
        rows = []
        for p, f in practitioners_with_flags:
            d = {
                "id": p.id,
                "provider": normalize_provider(p.provider),
                "title": p.title,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "name": (p.first_name or "") or (p.last_name or ""),
                "email": p.email,
                "phone": p.phone,
                "notes": p.notes,
            }
            # overlay flags if exist, otherwise set defaults
            if f:
                d["training"]  = bool(getattr(f, "training", False))
                d["website"]   = bool(getattr(f, "website", False))
                d["whatsapp"]  = bool(getattr(f, "whatsapp", False))
                d["engagebay"] = bool(getattr(f, "engagebay", False))
                d["onboarded"] = bool(getattr(f, "onboarded", False))
            else:
                # Set default values if no flag record exists
                d["training"]  = False
                d["website"]   = False
                d["whatsapp"]  = False
                d["engagebay"] = False
                d["onboarded"] = False
            rows.append(d)
        
        # Apply filtering if requested
        if filter_param == 'onboarded':
            rows = [r for r in rows if r.get('onboarded', False)]
        elif filter_param == 'pending':
            rows = [r for r in rows if not r.get('onboarded', False)]
        
        buckets = _bucket_practitioners(rows)
    except Exception as e:
        app.logger.error(f"Failed to list practitioners: {e}")
        buckets = {'pending': {}, 'completed': {}}
    # Calculate stats for the template
    total_practitioners = len(rows)
    completed_count = sum(len(practitioners) for practitioners in buckets.get('completed', {}).values())
    pending_count = sum(len(practitioners) for practitioners in buckets.get('pending', {}).values())
    provider_count = len(set(p.get('provider') for p in rows))
    
    return render_template("practitioners.html", 
                         user=user, 
                         buckets=buckets,
                         total_practitioners=total_practitioners,
                         completed_count=completed_count,
                         pending_count=pending_count,
                         provider_count=provider_count)

@app.route("/api/practitioners", methods=["GET"])
def api_practitioners():
    """API endpoint for lazy loading practitioners"""
    try:
        provider = request.args.get('provider')
        status = request.args.get('status', 'all')  # all, pending, completed
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        
        # Build query
        query = db.session.query(Practitioner, PractitionerFlag).outerjoin(
            PractitionerFlag, Practitioner.id == PractitionerFlag.pid
        )
        
        if provider:
            query = query.filter(Practitioner.provider == provider)
        
        # Filter by status
        if status == 'pending':
            query = query.filter(or_(PractitionerFlag.onboarded == False, PractitionerFlag.onboarded.is_(None)))
        elif status == 'completed':
            query = query.filter(PractitionerFlag.onboarded == True)
        
        # Paginate
        results = query.order_by(
            Practitioner.provider, Practitioner.last_name, Practitioner.first_name
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        practitioners_data = []
        for p, f in results.items:
            practitioner_data = {
                "id": p.id,
                "provider": normalize_provider(p.provider),
                "title": p.title,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "email": p.email,
                "phone": p.phone,
                "notes": p.notes,
                "training": bool(getattr(f, "training", False)) if f else False,
                "website": bool(getattr(f, "website", False)) if f else False,
                "whatsapp": bool(getattr(f, "whatsapp", False)) if f else False,
                "engagebay": bool(getattr(f, "engagebay", False)) if f else False,
                "onboarded": bool(getattr(f, "onboarded", False)) if f else False,
            }
            practitioners_data.append(practitioner_data)
        
        return jsonify({
            "practitioners": practitioners_data,
            "pagination": {
                "page": results.page,
                "pages": results.pages,
                "per_page": results.per_page,
                "total": results.total,
                "has_next": results.has_next,
                "has_prev": results.has_prev
            }
        })
        
    except Exception as e:
        app.logger.error(f"API practitioners error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/practitioners/<int:pid>/update", methods=["POST"])
def practitioners_update(pid):
    # Handle both form and JSON requests
    try:
        flag = PractitionerFlag.query.filter_by(pid=pid).first()
        if not flag:
            flag = PractitionerFlag(pid=pid)
            db.session.add(flag)
        
        # Check if it's a JSON request (from flag clicking)
        if request.is_json:
            data = request.get_json()
            if 'training' in data:
                flag.training = data['training']
            if 'website' in data:
                flag.website = data['website']
            if 'whatsapp' in data:
                flag.whatsapp = data['whatsapp']
            if 'engagebay' in data:
                flag.engagebay = data['engagebay']
        else:
            # Handle form request (from edit page)
            flag.training  = 'training'  in request.form
            flag.website   = 'website'   in request.form
            flag.whatsapp  = 'whatsapp'  in request.form
            flag.engagebay = 'engagebay' in request.form
        
        flag.onboarded = bool(flag.training and flag.website and flag.whatsapp and flag.engagebay)
        flag.updated_at = datetime.utcnow()
        db.session.commit()
        
        if request.is_json:
            return jsonify({"success": True, "message": "Flag updated successfully"})
        else:
            flash("Practitioner flags updated.", "success")
            return redirect(url_for("practitioners") + ("#completed" if flag.onboarded else ""))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to persist PractitionerFlag for pid={pid}: {e}")
        if request.is_json:
            return jsonify({"success": False, "message": "Failed to update flag"}), 500
        else:
            flash("Failed to update flags.", "error")
            return redirect(url_for("practitioners"))

@app.post("/practitioners/<int:pid>/delete")
def practitioners_delete(pid):
    p = db.session.get(Practitioner, pid)
    if not p:
        flash("Practitioner not found.", "error")
        return redirect(url_for("practitioners"))
    try:
        # Remove flags first (if exist) to avoid orphan rows
        flag = PractitionerFlag.query.filter_by(pid=pid).first()
        if flag:
            db.session.delete(flag)
        db.session.delete(p)
        db.session.commit()
        flash("Practitioner deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete practitioner.", "error")
    return redirect(url_for("practitioners"))
@app.route("/practitioners/new", methods=["GET","POST"])
def practitioners_new():
    if request.method == "POST":
        p = Practitioner(
            provider=normalize_provider(request.form.get("provider") or ""),
            title=request.form.get("title") or "",
            first_name=request.form.get("first_name") or "",
            last_name=request.form.get("last_name") or "",
            email=request.form.get("email") or "",
            phone=request.form.get("phone") or "",
            notes=request.form.get("notes") or "",
        )
        try:
            db.session.add(p)
            db.session.commit()
            flash("Practitioner added.", "success")
            return redirect(url_for("practitioners"))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Failed to create practitioner: {e}")
            flash("Failed to add practitioner.", "error")
    return render_template("practitioner_new.html")

@app.route("/orders", endpoint="orders")
def orders_view():
    filter_param = request.args.get('filter')  # Get filter parameter from URL
    
    if DEMO_MODE:
        seed_demo_if_empty()
        migrate_orders_to_db()

    db_orders = db.session.query(Order).order_by(Order.created_at.desc()).all()
    orders = []
    for o in db_orders:
        opt_in = o.opt_in_status
        # Normalize "Pending" or empty string to None
        if opt_in and opt_in.strip().lower() == "pending":
            opt_in = None
        orders.append({
            "id": o.id, "provider": o.provider, "name": o.name, "surname": o.surname,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
            "created_at": o.created_at or datetime.now(timezone.utc),
            "status": o.status, "opt_in_status": (opt_in if opt_in and opt_in.strip() else None), "notes": o.notes or "",
            "email_status": o.email_status or "ok",
            "sent_out": o.sent_out, "received_back": o.received_back, "kit_registered": o.kit_registered,
            "results_sent": o.results_sent, "paid": o.paid, "invoiced": o.invoiced,
            "practitioner_name": o.practitioner_name or "",
            "items": [{"sku": it.sku, "qty": it.qty} for it in o.items],
            "time_left": time_left({"created_at": o.created_at or datetime.now(timezone.utc)}),
            # WooCommerce fields
            "woocommerce_id": o.woocommerce_id,
            "customer_name": o.customer_name,
            "customer_email": o.customer_email,
            "customer_phone": o.customer_phone,
            "address": o.address,
            "items_description": o.items_description,
            "total_amount": o.total_amount,
            "order_date": o.order_date.isoformat() if o.order_date else None,
            "payment_method": o.payment_method,
            "is_woocommerce": bool(o.woocommerce_id),
        })
    
    # Apply filtering if requested
    if filter_param == 'completed':
        orders = [o for o in orders if o.get('status', '').lower().find('completed') != -1]
    elif filter_param == 'pending':
        orders = [o for o in orders if o.get('status', '').lower().find('completed') == -1 and o.get('status', '').lower().find('cancel') == -1]
    elif filter_param == 'woocommerce':
        orders = [o for o in orders if o.get('is_woocommerce', False)]
    
    assigned_units = {}
    for ou in OrderUnit.query.all():
        assigned_units.setdefault(ou.order_id, []).append(ou)


    # Build tab/provider buckets so the template can render fast and correctly
    buckets = {'pending': {}, 'completed': {}}
    for o in orders:
        tab = bucket_order(o)
        prov = o.get('provider') or 'Unassigned'
        if prov not in buckets[tab]:
            buckets[tab][prov] = []
        buckets[tab][prov].append(o)
    # Sort providers alphabetically and orders by created date descending
    for tab in buckets:
        buckets[tab] = dict(sorted(buckets[tab].items(), key=lambda kv: kv[0]))
        for prov, rows in buckets[tab].items():
            rows.sort(key=lambda r: r.get('created_at') or '', reverse=True)

    # Calculate stats for the template
    pending_orders_count = sum(len(orders) for orders in buckets.get('pending', {}).values())
    completed_orders_count = sum(len(orders) for orders in buckets.get('completed', {}).values())
    assigned_units_count = sum(len(units) for units in assigned_units.values())
    required_units_count = sum(len(order.get('items', [])) for order in orders)
    
    # Create assigned and required dictionaries for template
    assigned = {}
    required = {}
    for order in orders:
        assigned[order['id']] = len(assigned_units.get(order['id'], []))
        required[order['id']] = len(order.get('items', []))
    
    return render_template("orders.html",
                        user=session.get("user"),
                        orders=orders,
                        assigned_units=assigned_units,
                        call_logs=OrderCallLog.query.all(),
                        buckets=buckets,
                        assigned=assigned,
                        required=required,
                        pending_orders_count=pending_orders_count,
                        completed_orders_count=completed_orders_count,
                        assigned_units_count=assigned_units_count,
                        required_units_count=required_units_count)
@app.route("/stock")
def stock():
    user = session.get("user")
    
    try:
        # Optimized query: get all stock items
        items = StockItem.query.order_by(StockItem.id.desc()).all()
        
        # Get all stock units in one query
        stock_units = StockUnit.query.all()
        
        # Build counts dictionary efficiently
        counts = {}
        batch_summary = {}
        by_provider = {}
        
        for i in items:
            # Count units for this item
            item_units = [u for u in stock_units if u.item_id == i.id]
            total = len(item_units)
            in_stock = len([u for u in item_units if u.status == "In Stock"])
            counts[i.id] = {"total": total, "in_stock": in_stock}
            
            # Group by provider
            prov = normalize_provider(i.provider) or "Unassigned"
            by_provider.setdefault(prov, []).append(i)
            
            # Simple batch summary (avoid complex query)
            batch_numbers = set(u.batch_number for u in item_units if u.batch_number)
            if not batch_numbers:
                batch_summary[i.id] = "-"
            elif len(batch_numbers) == 1:
                batch_summary[i.id] = list(batch_numbers)[0]
            else:
                batch_summary[i.id] = f"Mixed ({len(batch_numbers)})"
        
        providers_sorted = sorted([p for p in by_provider.keys() if p != "Unassigned"]) + (["Unassigned"] if "Unassigned" in by_provider else [])
        
        # Calculate stats for the template
        total_items = len(items)
        total_units = sum(counts[item.id]['in_stock'] for item in items)
        low_stock_count = sum(1 for item in items if counts[item.id]['in_stock'] < 10)
        
        return render_template("stock.html",
                             user=user,
                             counts=counts,
                             by_provider=by_provider,
                             providers=providers_sorted,
                             batch_summary=batch_summary,
                             total_items=total_items,
                             total_units=total_units,
                             low_stock_count=low_stock_count)
    except Exception as e:
        app.logger.error(f"Stock route error: {e}")
        # Return empty data if there's an error
        return render_template("stock.html", 
                             user=user, 
                             counts={}, 
                             by_provider={}, 
                             providers=[], 
                             batch_summary={}, 
                             total_items=0, 
                             total_units=0, 
                             low_stock_count=0)

@app.route("/new")
def new_item():
    user = session.get("user")
    return render_template("new_item.html", user=user)

@app.post("/items")
def create_item():
    try:
        # Log ALL form data for debugging
        form_data = dict(request.form)
        app.logger.info(f"Create item called - ALL Form data: {form_data}")
        print(f"DEBUG: Form data keys: {list(form_data.keys())}")
        print(f"DEBUG: Full form data: {form_data}")
        
        # Check specifically for barcode-related fields
        for key in request.form.keys():
            if 'barcode' in key.lower() or 'quantity' in key.lower() or 'quant' in key.lower():
                print(f"DEBUG: Found field '{key}' = '{request.form.get(key)}'")
        
        # Normalize and validate incoming fields
        name = (request.form.get("name") or "").strip()
        expiry = parse_date(request.form.get("expiry_date"))
        received = parse_date(request.form.get("received_date"))
        code_type = (request.form.get("code_type") or "Kit").strip()
        # Normalize plural vs singular to fit legacy DBs with VARCHAR(10)
        if code_type.lower().startswith("supplement"):
            code_type = "Supplement"  # 10 chars
        if len(code_type) > 20:
            flash("Code Type is too long (max 20).", "error")
            return redirect(url_for("new_item"))
        person_requested = (request.form.get("person_requested") or None)
        req_dt_str = request.form.get("request_datetime")
        req_dt = None
        if req_dt_str:
            try:
                # Parse and convert to naive datetime (remove timezone info)
                req_dt = datetime.strptime(req_dt_str, "%Y-%m-%dT%H:%M")
            except (ValueError, AttributeError):
                try:
                    # Try ISO format but remove timezone
                    parsed = datetime.fromisoformat(req_dt_str.replace('Z', '+00:00'))
                    req_dt = parsed.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    req_dt = None
        provider = normalize_provider(request.form.get("provider")) or "Unassigned"
        batch_number = (request.form.get("batch_number") or "").strip() or None

        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("new_item"))

        # Create the stock item
        item = StockItem(
            name=name,
            expiry_date=expiry,
            received_date=received,
            code_type=code_type,
            person_requested=person_requested,
            request_datetime=req_dt,
            current_stock=0,  # Will be set based on barcodes added
            provider=provider,
        )
        db.session.add(item)
        db.session.flush()  # Get the ID
        
        app.logger.info(f"Stock item created with ID: {item.id}")
        
        # Process barcodes
        barcodes_added = 0
        barcode_list = []
        
        # Option 1: Single barcode + quantity
        # Support both field names: "barcode" and "shared_barcode"
        single_barcode = (request.form.get("shared_barcode") or request.form.get("barcode") or "").strip()
        # Support multiple possible field names for quantity
        quantity_str = (request.form.get("shared_barcode_quantity") or request.form.get("quantity") or request.form.get("shared_quantity") or request.form.get("multi_quantity") or "").strip()
        
        app.logger.info(f"Barcode: '{single_barcode}', Quantity: '{quantity_str}'")
        
        # Check if user is using Option 1 (BOTH fields must be filled)
        if single_barcode and quantity_str:
            try:
                quantity = int(quantity_str)
                app.logger.info(f"Parsed quantity: {quantity}")
                
                if quantity <= 0:
                    flash("Quantity must be greater than 0.", "error")
                    db.session.rollback()
                    return redirect(url_for("new_item"))
                    
                # Add the same barcode multiple times
                for i in range(quantity):
                    barcode_list.append(single_barcode)
                    
                app.logger.info(f"Created barcode_list with {len(barcode_list)} items")
            except (ValueError, TypeError) as e:
                app.logger.error(f"Quantity parsing error: {e}")
                flash("Invalid quantity. Please enter a whole number.", "error")
                db.session.rollback()
                return redirect(url_for("new_item"))
        # Check if only one field is filled (incomplete Option 1)
        elif single_barcode or quantity_str:
            if not single_barcode:
                flash("Please enter a barcode for Option 1, or use Option 2 instead.", "error")
                db.session.rollback()
                return redirect(url_for("new_item"))
            if not quantity_str:
                flash("Please enter a quantity for Option 1, or use Option 2 instead.", "error")
                db.session.rollback()
                return redirect(url_for("new_item"))
        else:
            # Option 2: Manual barcode entry
            barcodes_text = request.form.get("barcodes", "").strip()
            app.logger.info(f"Manual barcodes text: '{barcodes_text}'")
            if barcodes_text:
                # Parse barcodes - support both newline and comma separated
                for line in barcodes_text.split('\n'):
                    line = line.strip()
                    if ',' in line:
                        # Comma-separated values
                        barcode_list.extend([b.strip() for b in line.split(',') if b.strip()])
                    elif line:
                        # Single barcode per line
                        barcode_list.append(line)
        
        # Add stock units for each barcode in the list
        app.logger.info(f"Barcode list contains {len(barcode_list)} items")
        
        if barcode_list:
            for barcode in barcode_list:
                unit = StockUnit(
                    barcode=barcode,
                    batch_number=batch_number,
                    status="In Stock",
                    item_id=item.id,
                    last_update=datetime.utcnow()
                )
                db.session.add(unit)
                barcodes_added += 1
                app.logger.info(f"Added unit {barcodes_added} with barcode: {barcode}")
            
            # Update current_stock count
            item.current_stock = barcodes_added
        
        app.logger.info(f"Committing {barcodes_added} units to database")
        db.session.commit()
        app.logger.info("Commit successful!")
        
        if barcodes_added > 0:
            flash(f"Stock item '{name}' added with {barcodes_added} unit(s).", "success")
        else:
            flash(f"Stock item '{name}' added. No units were added.", "success")
        
        app.logger.info(f"Redirecting to stock page")
        return redirect(url_for("stock"))
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app.logger.error(f"===== EXCEPTION in create_item =====")
        app.logger.error(f"Error: {str(e)}")
        app.logger.error(f"Traceback:\n{tb}")
        db.session.rollback()
        flash(f"ERROR creating stock item: {str(e)}", "error")
        return redirect(url_for("new_item"))

@app.route("/item/<int:item_id>/units")
def manage_units(item_id):
    user = session.get("user")
    item = StockItem.query.get_or_404(item_id)
    units = StockUnit.query.filter_by(item_id=item_id).order_by(StockUnit.id.desc()).all()
    
    # Get Sales Order PDFs for this page
    try:
        pdfs = SalesOrderPDF.query.order_by(SalesOrderPDF.uploaded_at.desc()).all()
    except Exception as pdf_error:
        app.logger.warning(f"SalesOrderPDF table not found or error: {pdf_error}")
        pdfs = []
    
    return render_template("units.html", user=user, item=item, units=units, pdfs=pdfs)

@app.post("/item/<int:item_id>/units/add_one")
def add_unit_one(item_id):
    item = StockItem.query.get_or_404(item_id)
    barcode = (request.form.get("barcode") or "").strip()
    batch_number = (request.form.get("batch_number") or "").strip() or None
    if not barcode:
        flash("Scan or enter a barcode.", "error"); return redirect(url_for("manage_units", item_id=item_id))
    if StockUnit.query.filter_by(barcode=barcode).first():
        flash("This barcode already exists.", "error"); return redirect(url_for("manage_units", item_id=item_id))

    # Optional: update item-level dates when adding a unit
    expiry = parse_date(request.form.get("expiry_date"))
    received = parse_date(request.form.get("received_date"))
    if expiry:
        item.expiry_date = expiry
    if received:
        item.received_date = received
    u = StockUnit(barcode=barcode, batch_number=batch_number, item_id=item_id, status="In Stock", last_update=datetime.now(timezone.utc))
    db.session.add(u); db.session.commit()
    flash(f"Added barcode {barcode}.", "success")
    return redirect(url_for("manage_units", item_id=item_id))

@app.post("/item/<int:item_id>/units/add_bulk")
def add_units_bulk(item_id):
    item = StockItem.query.get_or_404(item_id)
    raw = request.form.get("barcodes","")
    default_batch = (request.form.get("batch_number") or "").strip() or None

    # Optional: update item-level dates for this batch
    expiry = parse_date(request.form.get("expiry_date"))
    received = parse_date(request.form.get("received_date"))
    if expiry:
        item.expiry_date = expiry
    if received:
        item.received_date = received
    new_count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line: 
            continue
        parts = [p.strip() for p in re.split(r'[,	|]+', line, maxsplit=1) if p.strip()]
        barcode = parts[0] if parts else ""
        if not barcode:
            continue
        batch_no = parts[1] if len(parts) > 1 else default_batch
        if StockUnit.query.filter_by(barcode=barcode).first():
            continue
        db.session.add(StockUnit(barcode=barcode, batch_number=batch_no, item_id=item_id, status="In Stock", last_update=datetime.now(timezone.utc)))
        new_count += 1
    db.session.commit()
    flash(f"Added {new_count} barcodes.", "success")
    return redirect(url_for("manage_units", item_id=item_id))

@app.post("/unit/<int:unit_id>/delete")
def delete_unit(unit_id):
    u = StockUnit.query.get_or_404(unit_id)
    if OrderUnit.query.filter_by(unit_id=unit_id).first():
        flash("Cannot delete: unit assigned to order.", "error")
        return redirect(url_for("manage_units", item_id=u.item_id))
    item_id = u.item_id
    db.session.delete(u); db.session.commit()
    flash("Unit deleted.", "success")
    return redirect(url_for("manage_units", item_id=item_id))

@app.post("/units/<int:unit_id>/sign-out-promotional")
def sign_out_promotional(unit_id):
    """Sign out a stock unit for promotional use"""
    u = StockUnit.query.get_or_404(unit_id)
    
    signed_out_by = (request.form.get("signed_out_by") or "").strip()
    promotional_notes = (request.form.get("promotional_notes") or "").strip()
    
    if not signed_out_by or not promotional_notes:
        flash("Please provide your name and purpose for promotional use.", "error")
        return redirect(url_for("manage_units", item_id=u.item_id))
    
    u.promotional_use = True
    u.signed_out_by = signed_out_by
    u.signed_out_date = datetime.now()
    u.promotional_notes = promotional_notes
    u.status = "Promotional Use"
    u.last_update = datetime.now()
    
    db.session.commit()
    flash(f"✓ Barcode {u.barcode} signed out for promotional use by {signed_out_by}", "success")
    return redirect(url_for("manage_units", item_id=u.item_id))

@app.post("/units/<int:unit_id>/return-promotional")
def return_promotional(unit_id):
    """Return a promotional stock unit"""
    u = StockUnit.query.get_or_404(unit_id)
    
    returned_by = (request.form.get("returned_by") or "").strip()
    return_reason = (request.form.get("return_reason") or "").strip()
    
    if not returned_by or not return_reason:
        flash("Please provide your name and condition notes.", "error")
        return redirect(url_for("manage_units", item_id=u.item_id))
    
    u.returned = True
    u.returned_by = returned_by
    u.returned_date = datetime.now()
    u.return_reason = return_reason
    u.promotional_use = False
    u.status = "In Stock"
    u.last_update = datetime.now()
    
    db.session.commit()
    flash(f"✓ Barcode {u.barcode} returned to stock by {returned_by}", "success")
    return redirect(url_for("manage_units", item_id=u.item_id))

# ---------------- Promotional Items (Gifts & Banners) ----------------

@app.route("/promotional-items")
def promotional_items():
    """Display the Gifts & Banners management page"""
    user = session.get("user")
    items = PromotionalItem.query.order_by(PromotionalItem.id.desc()).all()
    
    # Calculate stats
    total_items = len(items)
    available_count = sum(1 for item in items if not item.signed_out and item.available_quantity > 0)
    signed_out_count = sum(1 for item in items if item.signed_out)
    total_value = sum(item.cost or 0 for item in items)
    
    return render_template(
        "promotional_items.html",
        user=user,
        items=items,
        total_items=total_items,
        available_count=available_count,
        signed_out_count=signed_out_count,
        total_value=total_value
    )

@app.post("/promotional-items/add")
def add_promotional_item():
    """Add a new promotional item"""
    name = (request.form.get("name") or "").strip()
    category = (request.form.get("category") or "").strip()
    
    if not name or not category:
        flash("Name and category are required.", "error")
        return redirect(url_for("promotional_items"))
    
    item = PromotionalItem(
        name=name,
        category=category,
        description=(request.form.get("description") or "").strip() or None,
        quantity=int(request.form.get("quantity") or 1),
        available_quantity=int(request.form.get("available_quantity") or request.form.get("quantity") or 1),
        location=(request.form.get("location") or "").strip() or None,
        condition=(request.form.get("condition") or "Good").strip(),
        purchase_date=parse_date(request.form.get("purchase_date")),
        cost=float(request.form.get("cost") or 0) if request.form.get("cost") else None,
        notes=(request.form.get("notes") or "").strip() or None
    )
    
    db.session.add(item)
    db.session.commit()
    flash(f"✓ Added promotional item: {name}", "success")
    return redirect(url_for("promotional_items"))

@app.get("/promotional-items/<int:item_id>/json")
def get_promotional_item_json(item_id):
    """Get promotional item data as JSON for editing"""
    item = PromotionalItem.query.get_or_404(item_id)
    return jsonify({
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "quantity": item.quantity,
        "available_quantity": item.available_quantity,
        "location": item.location,
        "condition": item.condition,
        "purchase_date": item.purchase_date.isoformat() if item.purchase_date else None,
        "cost": float(item.cost) if item.cost else None,
        "notes": item.notes
    })

@app.post("/promotional-items/<int:item_id>/update")
def update_promotional_item(item_id):
    """Update an existing promotional item"""
    item = PromotionalItem.query.get_or_404(item_id)
    
    item.name = (request.form.get("name") or "").strip() or item.name
    item.category = (request.form.get("category") or "").strip() or item.category
    item.description = (request.form.get("description") or "").strip() or None
    item.quantity = int(request.form.get("quantity") or item.quantity)
    item.available_quantity = int(request.form.get("available_quantity") or item.available_quantity)
    item.location = (request.form.get("location") or "").strip() or None
    item.condition = (request.form.get("condition") or item.condition).strip()
    item.purchase_date = parse_date(request.form.get("purchase_date")) or item.purchase_date
    
    cost_input = request.form.get("cost")
    if cost_input:
        item.cost = float(cost_input)
    
    item.notes = (request.form.get("notes") or "").strip() or None
    
    db.session.commit()
    flash(f"✓ Updated {item.name}", "success")
    return redirect(url_for("promotional_items"))

@app.post("/promotional-items/<int:item_id>/sign-out")
def sign_out_promotional_item(item_id):
    """Sign out a promotional item"""
    item = PromotionalItem.query.get_or_404(item_id)
    
    if item.available_quantity < 1:
        flash("No items available to sign out.", "error")
        return redirect(url_for("promotional_items"))
    
    signed_out_by = (request.form.get("signed_out_by") or "").strip()
    sign_out_notes = (request.form.get("sign_out_notes") or "").strip()
    
    if not signed_out_by or not sign_out_notes:
        flash("Please provide your name and purpose.", "error")
        return redirect(url_for("promotional_items"))
    
    item.signed_out = True
    item.signed_out_by = signed_out_by
    item.signed_out_date = datetime.now()
    item.sign_out_notes = sign_out_notes
    item.expected_return_date = parse_date(request.form.get("expected_return_date"))
    item.available_quantity -= 1
    
    db.session.commit()
    flash(f"✓ {item.name} signed out to {signed_out_by}", "success")
    return redirect(url_for("promotional_items"))

@app.post("/promotional-items/<int:item_id>/return")
def return_promotional_item(item_id):
    """Return a signed out promotional item"""
    item = PromotionalItem.query.get_or_404(item_id)
    
    returned_by = (request.form.get("last_returned_by") or "").strip()
    return_notes = (request.form.get("return_notes") or "").strip()
    
    if not returned_by or not return_notes:
        flash("Please provide your name and condition notes.", "error")
        return redirect(url_for("promotional_items"))
    
    item.signed_out = False
    item.last_returned_by = returned_by
    item.last_returned_date = datetime.now()
    item.return_notes = return_notes
    item.available_quantity += 1
    
    # Clear sign-out fields
    item.signed_out_by = None
    item.signed_out_date = None
    item.sign_out_notes = None
    item.expected_return_date = None
    
    db.session.commit()
    flash(f"✓ {item.name} returned by {returned_by}", "success")
    return redirect(url_for("promotional_items"))

@app.post("/promotional-items/<int:item_id>/delete")
def delete_promotional_item(item_id):
    """Delete a promotional item"""
    item = PromotionalItem.query.get_or_404(item_id)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f"✓ Deleted {name}", "success")
    return redirect(url_for("promotional_items"))

# ---------------- Tasks ----------------

@app.get("/item/<int:item_id>/confirm-delete")
def confirm_delete_item(item_id):
    item = StockItem.query.get_or_404(item_id)
    # Count units & assigned units
    total_units = db.session.query(func.count(StockUnit.id)).filter(StockUnit.item_id==item_id).scalar() or 0
    assigned_units = (db.session.query(func.count(OrderUnit.id))
        .join(StockUnit, OrderUnit.unit_id==StockUnit.id)
        .filter(StockUnit.item_id==item_id).scalar()) or 0
    can_delete = (assigned_units == 0)
    return render_template(
        "confirm_delete.html",
        item=item,
        total_units=total_units,
        assigned_units=assigned_units,
        can_delete=can_delete
    )

@app.post("/item/<int:item_id>/delete")
def delete_item(item_id):
    item = StockItem.query.get_or_404(item_id)
    # Prevent deletion if any units are assigned to orders
    assigned = (db.session.query(OrderUnit)
        .join(StockUnit, OrderUnit.unit_id==StockUnit.id)
        .filter(StockUnit.item_id==item_id)
        .first())
    if assigned:
        flash("Cannot delete: some units are assigned to orders.", "error")
        return redirect(url_for("stock"))
    # Delete all units for this item, then the item
    units = StockUnit.query.filter_by(item_id=item_id).all()
    for u in units:
        db.session.delete(u)
    db.session.delete(item)
    db.session.commit()
    flash("Stock item and its unassigned barcodes deleted.", "success")
    return redirect(url_for("stock"))


@app.route("/tasks")
def tasks_home():
    user = session.get("user")
    q = Task.query.order_by(Task.status.desc(), Task.due_date.asc().nullslast(), Task.created_at.desc()).all()
    return render_template("tasks.html", user=user, tasks=q)

@app.post("/tasks/add")
def tasks_add():
    title = request.form.get("title","").strip()
    if not title:
        flash("Task needs a title.", "error"); return redirect(url_for("tasks_home"))
    t = Task(
        title=title,
        provider=normalize_provider(request.form.get("provider")) or None,
        assignee=request.form.get("assignee") or None,
        due_date=parse_date(request.form.get("due_date")),
        status=request.form.get("status") or "Open",
        notes=request.form.get("notes") or None
    )
    db.session.add(t); db.session.commit()
    flash("Task added.", "success")
    return redirect(url_for("tasks_home"))

@app.post("/tasks/<int:tid>/update")
def tasks_update(tid):
    t = Task.query.get_or_404(tid)
    t.title = request.form.get("title", t.title)
    t.provider = normalize_provider(request.form.get("provider")) or t.provider
    t.assignee = request.form.get("assignee") or t.assignee
    t.due_date = parse_date(request.form.get("due_date")) or t.due_date
    t.status = request.form.get("status") or t.status
    t.notes = request.form.get("notes") or t.notes
    db.session.commit()
    flash("Task updated.", "success")
    return redirect(url_for("tasks_home"))

@app.post("/tasks/<int:tid>/delete")
def tasks_delete(tid):
    t = Task.query.get_or_404(tid)
    db.session.delete(t); db.session.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("tasks_home"))

# ---------------- Reports (Excel Export) ----------------

@app.route("/reports")
def reports():
    user = session.get("user")
    
    # Get real data for reports
    try:
        # Practitioners data
        practitioners = Practitioner.query.all()
        practitioner_flags = PractitionerFlag.query.all()
        flags_dict = {f.pid: f for f in practitioner_flags}
        
        total_practitioners = len(practitioners)
        onboarded_count = sum(1 for p in practitioners if flags_dict.get(p.id) and flags_dict[p.id].onboarded)
        pending_count = total_practitioners - onboarded_count
        
        # Orders data
        orders = Order.query.all()
        total_orders = len(orders)
        completed_orders = sum(1 for o in orders if o.status == 'Completed')
        pending_orders = total_orders - completed_orders
        
        # Stock data
        stock_items = StockItem.query.all()
        total_stock_items = len(stock_items)
        stock_units = StockUnit.query.filter_by(status='In Stock').count()
        low_stock_items = []
        for item in stock_items:
            in_stock = StockUnit.query.filter_by(item_id=item.id, status='In Stock').count()
            if in_stock < 10:
                low_stock_items.append(item.name)
        
        # Files data from Document model (with error handling for schema mismatch)
        total_files = 0
        this_month_files = 0
        try:
            total_files = Document.query.count()
            this_month_files = Document.query.filter(
                Document.uploaded_at >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            ).count()
        except Exception as doc_error:
            app.logger.warning(f"Could not query Document table (likely schema mismatch): {doc_error}")
            # Use raw SQL query as fallback
            try:
                total_files = db.session.execute(text("SELECT COUNT(*) FROM document")).scalar()
                this_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                this_month_files = db.session.execute(
                    text("SELECT COUNT(*) FROM document WHERE uploaded_at >= :start"),
                    {"start": this_month_start}
                ).scalar()
            except Exception:
                pass  # Keep zeros if this fails too
        
        # Provider performance data
        provider_stats = {}
        for provider in set(p.provider for p in practitioners if p.provider):
            provider_practitioners = [p for p in practitioners if p.provider == provider]
            provider_orders = [o for o in orders if o.provider == provider]
            provider_completed = [o for o in provider_orders if o.status == 'Completed']
            
            provider_stats[provider] = {
                'practitioners': len(provider_practitioners),
                'orders': len(provider_orders),
                'completed': len(provider_completed)
            }
        
        # Create stats object for template
        stats = {
            'practitioners': {
                'total': total_practitioners,
                'onboarded': onboarded_count,
                'pending': pending_count
            },
            'orders': {
                'total': total_orders,
                'completed': completed_orders,
                'pending': pending_orders,
                'avg_time': 7.2  # Placeholder - calculate actual average
            },
            'stock': {
                'total_units': stock_units,
                'low_stock_items': low_stock_items,
                'expiring_items': [],  # Add logic to find expiring items
                'utilized': stock_units * 0.85  # Placeholder
            },
            'files': {
                'total': total_files,
                'this_month': this_month_files
            }
        }
        
        return render_template("reports.html", 
                             user=user, 
                             stats=stats, 
                             providers=list(provider_stats.keys()),
                             provider_stats=provider_stats)
    except Exception as e:
        app.logger.error(f"Failed to load reports data: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        # Return with empty data if there's an error
        return render_template("reports.html", 
                             user=user, 
                             stats=None, 
                             providers=[], 
                             provider_stats={})

def _wb_from_list_dict(rows, headers):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])
    return wb

@app.route("/export/practitioners.xlsx")
def export_practitioners():
    if DEMO_MODE:
        seed_demo_if_empty()
    try:
        overlay_practitioner_flags()
    except Exception as e:
        app.logger.warning(f"Overlay failed in export: {e}")
    rows = []
    for p in PRACTITIONERS:
        rows.append({
            "ID": p["id"],
            "Provider": p["provider"],
            "Name": f"{p.get('name') or p.get('first_name','')} {p.get('surname') or p.get('last_name','')}".strip(),
            "Email": p.get("email",""),
            "Phone": p.get("phone") or p.get("phone_e164",""),
            "SignedUp": p.get("signed_up",""),
            "Onboarded": "Yes" if p.get("onboarded") else "No",
            "Training": "Yes" if p.get("training") else "No",
            "Website": "Yes" if p.get("website") else "No",
            "WhatsApp": "Yes" if p.get("whatsapp") else "No",
            "EngageBay": "Yes" if p.get("engagebay") else "No",
            "Notes": p.get("notes",""),
        })
    headers = ["ID","Provider","Name","Email","Phone","SignedUp","Onboarded","Training","Website","WhatsApp","EngageBay","Notes"]
    wb = _wb_from_list_dict(rows, headers)
    bio = BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="practitioners.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/export/orders.xlsx")
def export_orders():
    if DEMO_MODE:
        seed_demo_if_empty()
    rows = []
    for o in ORDERS:
        rows.append({
            "ID": o["id"],
            "Provider": o["provider"],
            "Name": f"{o['name']} {o['surname']}",
            "OrderedAt": o["ordered_at"],
            "Status": o["status"],
            "SentOut": "Yes" if o["sent_out"] else "No",
            "ReceivedBack": "Yes" if o["received_back"] else "No",
            "KitRegistered": "Yes" if o["kit_registered"] else "No",
            "ResultsSent": "Yes" if o["results_sent"] else "No",
            "Paid": "Yes" if o["paid"] else "No",
            "Invoiced": "Yes" if o["invoiced"] else "No",
            "PractitionerName": o["practitioner_name"],
            "Items": "; ".join([f"{it['sku']} x{it['qty']}" for it in o["items"]]),
            "Notes": o["notes"],
        })
    headers = ["ID","Provider","Name","OrderedAt","Status","SentOut","ReceivedBack","KitRegistered","ResultsSent","Paid","Invoiced","PractitionerName","Items","Notes"]
    wb = _wb_from_list_dict(rows, headers)
    bio = BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="orders.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------- Uploads (by provider) ----------------

@app.route("/uploads")
def uploads_home():
    user = session.get("user")
    files_by_provider = {}
    try:
        for p in PROVIDERS:
            try:
                rows = Document.query.filter_by(provider=p).order_by(Document.uploaded_at.desc()).all()
                files_by_provider[p] = rows
            except Exception as e:
                app.logger.error(f"Error loading files for provider {p}: {e}")
                files_by_provider[p] = []
        return render_template("uploads.html", user=user, providers=PROVIDERS, files_by_provider=files_by_provider)
    except Exception as e:
        app.logger.error(f"Error in uploads_home: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        flash(f"Error loading uploads: {str(e)}", "error")
        return render_template("uploads.html", user=user, providers=PROVIDERS, files_by_provider={})

@app.route("/sales-order-pdfs/upload", methods=["POST"])
def upload_sales_order_pdf():
    """Upload a new Sales Order PDF"""
    user = session.get("user")
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    # Read file data
    file_data = file.read()
    file_size = len(file_data)
    
    # Validate file size (max 10MB)
    if file_size > 10 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 10MB)'}), 400
    
    # Create new PDF record
    pdf = SalesOrderPDF(
        filename=file.filename,
        file_data=file_data,
        file_size=file_size,
        uploaded_by=user.get('name', user.get('preferred_username', 'Unknown'))
    )
    
    try:
        db.session.add(pdf)
        db.session.commit()
        return jsonify({'success': True, 'message': 'PDF uploaded successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route("/sales-order-pdfs/download/<int:pdf_id>")
def download_sales_order_pdf(pdf_id):
    """Download a Sales Order PDF"""
    user = session.get("user")
    if not user:
        return redirect(url_for('login'))
    
    pdf = SalesOrderPDF.query.get_or_404(pdf_id)
    
    return send_file(
        BytesIO(pdf.file_data),
        as_attachment=True,
        download_name=pdf.filename,
        mimetype='application/pdf'
    )

@app.route("/sales-order-pdfs/delete/<int:pdf_id>", methods=["POST"])
def delete_sales_order_pdf(pdf_id):
    """Delete a Sales Order PDF"""
    user = session.get("user")
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    pdf = SalesOrderPDF.query.get_or_404(pdf_id)
    
    try:
        db.session.delete(pdf)
        db.session.commit()
        return jsonify({'success': True, 'message': 'PDF deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route("/woocommerce/sync", methods=["POST"])
def manual_woocommerce_sync():
    """Manual WooCommerce sync endpoint"""
    user = session.get("user")
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        from woocommerce_integration import sync_woocommerce_orders
        
        # Get days parameter (default to 1 day)
        days = request.json.get('days', 1) if request.is_json else 1
        
        result = sync_woocommerce_orders(days_back=days)
        
        if result['success']:
            return jsonify({
                "success": True,
                "message": f"Sync completed: {result['new_orders']} new, {result['updated_orders']} updated",
                "data": result
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        app.logger.error(f"Manual WooCommerce sync error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/woocommerce/status")
def woocommerce_status():
    """Get WooCommerce integration status"""
    user = session.get("user")
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # Count WooCommerce orders
        wc_orders = Order.query.filter(Order.woocommerce_id.isnot(None)).count()
        total_orders = Order.query.count()
        
        # Get latest WooCommerce order
        latest_wc_order = Order.query.filter(Order.woocommerce_id.isnot(None)).order_by(Order.order_date.desc()).first()
        
        return jsonify({
            "success": True,
            "woocommerce_orders": wc_orders,
            "total_orders": total_orders,
            "latest_woocommerce_order": {
                "id": latest_wc_order.woocommerce_id,
                "customer": latest_wc_order.customer_name,
                "total": latest_wc_order.total_amount,
                "date": latest_wc_order.order_date.isoformat() if latest_wc_order.order_date else None
            } if latest_wc_order else None
        })
        
    except Exception as e:
        app.logger.error(f"WooCommerce status error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/woocommerce")
def woocommerce_dashboard():
    """WooCommerce management dashboard"""
    user = session.get("user")
    if not user:
        return redirect(url_for('login'))
    
    try:
        # Get WooCommerce statistics
        wc_orders = Order.query.filter(Order.woocommerce_id.isnot(None)).count()
        total_orders = Order.query.count()
        
        # Get recent WooCommerce orders
        recent_orders = Order.query.filter(Order.woocommerce_id.isnot(None)).order_by(Order.order_date.desc()).limit(10).all()
        
        return render_template("woocommerce_dashboard.html", 
                             user=user,
                             wc_orders=wc_orders,
                             total_orders=total_orders,
                             recent_orders=recent_orders)
        
    except Exception as e:
        app.logger.error(f"WooCommerce dashboard error: {e}")
        flash("Error loading WooCommerce dashboard", "error")
        return redirect(url_for('dashboard'))

@app.post("/uploads/add")
def upload_file():
    provider = normalize_provider(request.form.get("provider")) or "Unassigned"
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file.", "error"); return redirect(url_for("uploads_home"))
    ext = f.filename.rsplit(".",1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        flash("File type not allowed.", "error"); return redirect(url_for("uploads_home"))
    
    # Read file content and store in database
    file_content = f.read()
    file_size = len(file_content)
    
    # Generate unique stored name
    stored = secure_filename(f"{uuid.uuid4().hex}_{f.filename}")
    
    # Determine content type
    content_type = f.content_type or 'application/octet-stream'
    
    # Store file in database
    doc = Document(
        provider=provider or "Unassigned",
        filename=f.filename,
        stored_name=stored,
        file_data=file_content,
        file_size=file_size,
        content_type=content_type
    )
    db.session.add(doc)
    db.session.commit()
    flash("File uploaded.", "success")
    return redirect(url_for("uploads_home"))

@app.route("/uploads/<provider>/<stored_name>")
def download_uploaded(provider, stored_name):
    # Look up file in database
    doc = Document.query.filter_by(provider=provider, stored_name=stored_name).first()
    if not doc:
        # Try to find by any provider name variant (for backward compatibility)
        norm = normalize_provider(provider) or provider
        doc = Document.query.filter_by(provider=norm, stored_name=stored_name).first()
        if not doc:
            # Try stored_name only (might be from old system)
            doc = Document.query.filter_by(stored_name=stored_name).first()
    
    if doc and doc.file_data:
        # Serve file from database
        response = make_response(doc.file_data)
        response.headers['Content-Type'] = doc.content_type or 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename="{doc.filename}"'
        response.headers['Content-Length'] = str(doc.file_size)
        return response
    abort(404)

@app.post("/uploads/<provider>/<stored_name>/delete")
def delete_uploaded(provider, stored_name):
    """Delete an uploaded document"""
    doc = Document.query.filter_by(provider=provider, stored_name=stored_name).first()
    if not doc:
        # Try to find by any provider name variant
        norm = normalize_provider(provider) or provider
        doc = Document.query.filter_by(provider=norm, stored_name=stored_name).first()
        if not doc:
            doc = Document.query.filter_by(stored_name=stored_name).first()
    
    if doc:
        filename = doc.filename
        db.session.delete(doc)
        db.session.commit()
        flash(f"File '{filename}' deleted successfully.", "success")
    else:
        flash("File not found.", "error")
    
    return redirect(url_for("uploads_home"))

# ---------------- Azure demo auth (optional) ----------------
def _build_msal_app(cache=None, authority=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=authority or AUTHORITY,
        client_credential=CLIENT_SECRET, token_cache=cache
    )

def _build_auth_url(scopes=None, state=None):
    from flask import url_for
    return _build_msal_app().get_authorization_request_url(
        scopes or ["User.Read"],
        state=state or "default",
        redirect_uri=url_for("authorized", _external=True)
    )

@app.route("/login")
def login():
    client_id = os.environ.get("AZURE_CLIENT_ID") or CLIENT_ID
    if not client_id:
        try:
            from pathlib import Path as _P
            envp = _P(__file__).with_name(".env")
            app.logger.error("AZURE_CLIENT_ID missing. Expected in env or %s (exists=%s)", envp, envp.exists())
        except Exception:
            pass
    # Flag that we're in the middle of auth to help diagnose loops
    session["auth_in_progress"] = True
    session["state"] = secrets.token_urlsafe(16)
    return redirect(_build_auth_url(state=session["state"]))

@app.route(REDIRECT_PATH)
def authorized():
    # Callback from Microsoft
    error = request.args.get("error")
    if error:
        details = request.args.get("error_description", "")
        # Clear flag so before_request doesn't keep bouncing
        session.pop("auth_in_progress", None)
        return (f"<h2>Sign-in failed</h2><p>{error}: {details}</p>"
                f"<p><a href='{url_for('login')}'>Try again</a></p>"), 400

    if request.args.get("state") and session.get("state") and request.args.get("state") != session.get("state"):
        session.pop("auth_in_progress", None)
        return ("<h2>Sign-in failed</h2><p>Invalid state parameter.</p>"
                f"<p><a href='{url_for('login')}'>Try again</a></p>"), 400

    code = request.args.get("code")
    if not code:
        session.pop("auth_in_progress", None)
        return ("<h2>Sign-in failed</h2><p>No authorization code returned.</p>"
                f"<p><a href='{url_for('login')}'>Try again</a></p>"), 400

    try:
        cache = msal.SerializableTokenCache()
        result = _build_msal_app(cache=cache, authority=AUTHORITY).acquire_token_by_authorization_code(
            code,
            scopes=[SCOPE] if isinstance(SCOPE, str) else SCOPE,
            redirect_uri=url_for("authorized", _external=True),
        )
        if "error" in result:
            session.pop("auth_in_progress", None)
            return (f"<h2>Sign-in failed</h2><p>{result.get('error')}: {result.get('error_description')}</p>"
                    f"<p><a href='{url_for('login')}'>Try again</a></p>"), 400

        # Success
        id_claims = result.get("id_token_claims", {})
        session["id_claims"] = id_claims
        session["user"] = {
            "name": id_claims.get("name") or id_claims.get("preferred_username") or "User",
            "preferred_username": id_claims.get("preferred_username"),
            "oid": id_claims.get("oid"),
        }
        session["ms_access_token"] = result.get("access_token")
        session["ms_expires_in"] = result.get("expires_in")
        try:
            _now = int(time.time())
            _exp_in = int(result.get("expires_in") or 3600)
            session["ms_expires_at"] = _now + _exp_in
        except Exception:
            session["ms_expires_at"] = int(time.time()) + 3600

        session.permanent = True
        session.pop("auth_in_progress", None)
        flash(f"Signed in as {session['user'].get('preferred_username') or session['user'].get('name')}.", "success")
        return redirect(url_for("dashboard"))
    except Exception as e:
        session.pop("auth_in_progress", None)
        return (f"<h2>Sign-in failed</h2><p>Exception: {e}</p>"
                f"<p><a href='{url_for('login')}'>Try again</a></p>"), 500

@app.route("/logout")
def logout():
    session.clear()
    params = {"post_logout_redirect_uri": url_for("dashboard", _external=True)}
    authority = os.environ.get("AZURE_AUTHORITY", f"https://login.microsoftonline.com/{TENANT_ID}")
    return redirect(f"{authority}/oauth2/v2.0/logout?{urlencode(params)}")

# --- Global login enforcement ---
@app.before_request
def _require_login():
    # Allow these paths without auth
    allow_prefixes = ("/static/", "/favicon.ico")
    _rp = REDIRECT_PATH or "/getAToken"
    allow_exact = {"/login", "/logout", "/auth/diagnostics", "/health", "/healthz"}
    if _rp and _rp != "/":
        allow_exact.add(_rp)
    p = request.path or "/"
    if p.startswith(allow_prefixes) or p in allow_exact:
        return None
    if session.get("auth_in_progress"):
        return None
    # Only check if user exists, not MS token expiry - let Flask session handle timeout
    if not session.get("user"):
        session.clear()
        return redirect(url_for("login"))
    return None

@app.get("/orders/new")
def new_order_form():
    # Check authentication
    if not session.get("user") or not session.get("ms_expires_at") or int(time.time()) >= int(session.get("ms_expires_at")) - 60:
        session.clear()
        return redirect(url_for("login"))
    
    providers = ["Geneway","Optiway","Enbiosis","Reboot","Intelligene","Healthy Me","Intelligene Fedhealth","Geko"]
    # Get available stock items with their available units count
    try:
        stock_items = StockItem.query.order_by(StockItem.name).all()
        stock_items_data = []
        for item in stock_items:
            available_count = StockUnit.query.filter_by(item_id=item.id, status="In Stock").count()
            if available_count > 0:
                stock_items_data.append({
                    "id": item.id,
                    "name": item.name,
                    "provider": item.provider,
                    "available": available_count
                })
    except Exception as e:
        app.logger.error(f"Error loading stock items: {e}")
        stock_items_data = []
    
    return render_template("order_new.html", user=session.get("user"), providers=providers, stock_items=stock_items_data)

@app.post("/orders/new")
def create_order():
    # Check authentication
    if not session.get("user") or not session.get("ms_expires_at") or int(time.time()) >= int(session.get("ms_expires_at")) - 60:
        session.clear()
        return redirect(url_for("login"))
    
    provider = normalize_provider(request.form.get("provider"))
    name = (request.form.get("name") or "").strip()
    surname = (request.form.get("surname") or "").strip()
    practitioner_name = (request.form.get("practitioner_name") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    ordered_at_str = (request.form.get("ordered_at") or "").strip()
    try:
        ordered_at = datetime.fromisoformat(ordered_at_str) if ordered_at_str else datetime.now(timezone.utc)
    except Exception:
        ordered_at = datetime.now(timezone.utc)
    status = request.form.get("status") or "Pending"
    opt_in_status = request.form.get("opt_in_status") or None
    if opt_in_status and opt_in_status.strip().lower() == "pending":
        opt_in_status = None
    
    try:
        o = Order(provider=provider, name=name, surname=surname, practitioner_name=practitioner_name,
                notes=notes, ordered_at=ordered_at, status=status, opt_in_status=opt_in_status,
                created_at=datetime.now(timezone.utc))
        db.session.add(o); db.session.flush()

        # Assign actual stock units instead of SKU/qty
        for i in range(1, 4):
            stock_item_id = request.form.get(f"stock_item_{i}")
            qty = request.form.get(f"item_qty_{i}")
            if stock_item_id and qty:
                try:
                    item_id = int(stock_item_id)
                    q = int(qty)
                    # Find available StockUnits for this item
                    available_units = StockUnit.query.filter_by(item_id=item_id, status="In Stock").limit(q).all()
                    if len(available_units) < q:
                        flash(f"Only {len(available_units)} units available for selected item, requested {q}.", "warning")
                    for unit in available_units:
                        db.session.add(OrderUnit(order_id=o.id, unit_id=unit.id))
                        unit.status = "Assigned"
                        unit.last_update = datetime.now(timezone.utc)
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error assigning stock unit: {e}")
                    pass
        
        db.session.commit()
        flash(f"Order #{o.id} created.", "success")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating order: {e}")
        flash(f"Failed to create order: {str(e)}", "error")
    
    return redirect(url_for("orders"))

# ======== OpenRouter (optional) ========
OPENROUTER_API_KEY = (os.environ.get('OPENROUTER_API_KEY') or '').strip()
OPENROUTER_URL = (os.environ.get('OPENROUTER_URL') or 'https://openrouter.ai/api/v1/chat/completions').strip()
OPENROUTER_MODEL = (os.environ.get('OPENROUTER_MODEL') or 'openai/gpt-4o-mini').strip()
OPENROUTER_SITE_URL = (os.environ.get('OPENROUTER_SITE_URL') or '').strip()
OPENROUTER_TITLE = (os.environ.get('OPENROUTER_TITLE') or 'Life360 Dashboard Ask AI').strip()

def openrouter_complete(model, system, user, flask_request=None, timeout=60):
    # Call OpenRouter chat completions safely. Returns (ok, answer, error_str).
    if not OPENROUTER_API_KEY:
        return (False, '', 'OPENROUTER_API_KEY missing')

    try:
        site = OPENROUTER_SITE_URL or (flask_request.host_url.rstrip('/') if flask_request else '')
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'HTTP-Referer': site,
            'X-Title': OPENROUTER_TITLE or 'Life360 Dashboard Ask AI',
        }
        payload = {
            'model': model or OPENROUTER_MODEL,
            'messages': [
                {'role': 'system', 'content': system or ''},
                {'role': 'user', 'content': user or ''},
            ],
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            try:
                errj = resp.json()
                msg = errj.get('error', {}).get('message') or errj.get('message') or str(errj)
            except Exception:
                msg = resp.text[:500]
            return (False, '', f'{resp.status_code} from OpenRouter: {msg}')

        j = resp.json()
        choice0 = (j.get('choices') or [{}])[0]
        content = (choice0.get('message') or {}).get('content', '')
        if not content:
            return (False, '', 'No content in OpenRouter response')
        return (True, content, '')
    except requests.exceptions.RequestException as e:
        return (False, '', f'Network error: {e}')
    except Exception as e:
        return (False, '', f'Unexpected error: {e}')

@app.get("/orders/<int:order_id>/json")
def get_order_json(order_id):
    """Get order data as JSON for modal"""
    o = db.session.get(Order, order_id)
    if not o:
        return jsonify({"error": "Order not found"}), 404
    
    opt_in = o.opt_in_status
    # Normalize "Pending" or empty string to None
    if opt_in and opt_in.strip().lower() == "pending":
        opt_in = None
    
    # Get assigned units with item names
    assigned_units = []
    order_units = OrderUnit.query.filter_by(order_id=order_id).all()
    for ou in order_units:
        unit = ou.unit
        item = unit.item if unit else None
        assigned_units.append({
            "barcode": unit.barcode if unit else "",
            "status": unit.status if unit else "",
            "item_name": item.name if item else "Unknown",
            "provider": item.provider if item else ""
        })
    
    return jsonify({
        "id": o.id,
        "practitioner_name": o.practitioner_name or "",
        "status": o.status,
        "opt_in_status": (opt_in if opt_in and opt_in.strip() else None),
        "notes": o.notes or "",
        "sent_out": o.sent_out,
        "received_back": o.received_back,
        "kit_registered": o.kit_registered,
        "results_sent": o.results_sent,
        "paid": o.paid,
        "invoiced": o.invoiced,
        "pop_received": o.pop_received,
        "payment_received": o.payment_received,
        "awaiting_payment": o.awaiting_payment,
        "payment_notes": o.payment_notes or "",
        "payment_date": o.payment_date.isoformat() if o.payment_date else None,
        "assigned_units": assigned_units
    })

@app.post("/orders/<int:order_id>/update", endpoint="update_order")
def orders_update(order_id):
    o = db.session.get(Order, order_id)
    if not o:
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        o.practitioner_name = (data.get("practitioner_name") or o.practitioner_name or "").strip() or None
        o.status = (data.get("status") or o.status or "Pending").strip()
        opt_in_val = data.get("opt_in_status")
        o.opt_in_status = (opt_in_val.strip() if opt_in_val and isinstance(opt_in_val, str) and opt_in_val.strip() else None)
        o.notes = (data.get("notes") or o.notes or "").strip() or None
        o.sent_out = data.get("sent_out", False)
        o.received_back = data.get("received_back", False)
        o.kit_registered = data.get("kit_registered", False)
        o.results_sent = data.get("results_sent", False)
        o.paid = data.get("paid", False)
        o.invoiced = data.get("invoiced", False)
        
        # Payment tracking fields
        o.pop_received = data.get("pop_received", False)
        o.payment_received = data.get("payment_received", False)
        o.awaiting_payment = data.get("awaiting_payment", False)
        o.payment_notes = (data.get("payment_notes") or o.payment_notes or "").strip() or None
        
        # Set payment_date when payment_received is set to True
        if data.get("payment_received") and not o.payment_date:
            from datetime import datetime
            o.payment_date = datetime.now()
        
        # --- Auto-compute completion status for JSON requests ---
        all_done = bool(o.sent_out and o.received_back and o.kit_registered and o.results_sent and o.paid and o.invoiced)
        if all_done and not o.status.lower().startswith("completed"):
            o.status = "Completed"
        if o.status.lower().startswith("completed") and not o.completed_at:
            try:
                o.completed_at = datetime.now(timezone.utc)
            except Exception:
                from datetime import datetime as _dt
                o.completed_at = _dt.utcnow()
        elif not o.status.lower().startswith("completed"):
            o.completed_at = None
        
        db.session.commit()
        return jsonify({"success": True})
    else:
        o.practitioner_name = (request.form.get("practitioner_name") or o.practitioner_name or "").strip() or None
        o.status = (request.form.get("status") or o.status or "Pending").strip()
        opt_in_val = request.form.get("opt_in_status")
        o.opt_in_status = (opt_in_val.strip() if opt_in_val and isinstance(opt_in_val, str) and opt_in_val.strip() else None)
        o.notes = (request.form.get("notes") or o.notes or "").strip() or None

        def as_bool(name):
            v = request.form.get(name)
            return True if v in ("on","true","1","yes") else False
        o.sent_out = as_bool("sent_out")
        o.received_back = as_bool("received_back")
        o.kit_registered = as_bool("kit_registered")
        o.results_sent = as_bool("results_sent")
        o.paid = as_bool("paid")
        o.invoiced = as_bool("invoiced")
        
        # Payment tracking fields
        o.pop_received = as_bool("pop_received")
        o.payment_received = as_bool("payment_received")
        o.awaiting_payment = as_bool("awaiting_payment")
        o.payment_notes = (request.form.get("payment_notes") or o.payment_notes or "").strip() or None
        
        # Set payment_date when payment_received is set to True
        if as_bool("payment_received") and not o.payment_date:
            from datetime import datetime
            o.payment_date = datetime.now()

    # --- Auto-compute completion status ---
    all_done = bool(o.sent_out and o.received_back and o.kit_registered and o.results_sent and o.paid and o.invoiced)
    # If all operational flags are true, force status to 'Completed' and timestamp it.
    if all_done and not o.status.lower().startswith("completed"):
        o.status = "Completed"
    # Maintain a completion timestamp for dashboard/analytics.
    if o.status.lower().startswith("completed") and not o.completed_at:
        try:
            o.completed_at = datetime.now(timezone.utc)
        except Exception:
            # Fallback in case timezone isn't imported in this scope
            from datetime import datetime as _dt
            o.completed_at = _dt.utcnow()


    if o.status.lower().startswith("completed"):
        if not o.completed_at:
            o.completed_at = datetime.now(timezone.utc)
    else:
        o.completed_at = None

    o.email_status = (request.form.get("email_status") or o.email_status or "").strip() or None

    db.session.commit()
    flash(f"Order #{o.id} updated.", "success")
    return redirect(url_for("orders") + f"?tab=completed#o{o.id}")

@app.post("/orders/<int:order_id>/add_calllog", endpoint="add_calllog")
def orders_add_calllog(order_id):
    o = db.session.get(Order, order_id)
    if not o:
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    author = (request.form.get("author") or "").strip() or None
    summary = (request.form.get("summary") or "").strip()
    outcome = (request.form.get("outcome") or "").strip() or None
    if not summary:
        flash("Call log requires a summary.", "error")
        return redirect(url_for("orders") + f"#o{order_id}")
    cl = OrderCallLog(order_id=order_id, author=author, summary=summary, outcome=outcome)
    db.session.add(cl)
    db.session.commit()
    flash("Call log added.", "success")
    return redirect(url_for("orders") + f"#o{order_id}")

@app.post("/orders/<int:order_id>/assign")
def assign_unit(order_id):
    barcode = (request.form.get("barcode") or "").strip()
    if not barcode:
        flash("Scan or enter a barcode.", "error")
        return redirect(url_for("orders") + f"#o{order_id}")

    unit = StockUnit.query.filter_by(barcode=barcode).first()
    if not unit:
        flash("Barcode not found in stock.", "error")
        return redirect(url_for("orders") + f"#o{order_id}")

    if unit.status != "In Stock":
        flash(f"Unit {barcode} is not available (status: {unit.status}).", "error")
        return redirect(url_for("orders") + f"#o{order_id}")

    db.session.add(OrderUnit(order_id=order_id, unit_id=unit.id))
    unit.status = "Assigned"
    unit.last_update = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Assigned {barcode} to order #{order_id}.", "success")
    return redirect(url_for("orders") + f"#o{order_id}")

@app.post("/orders/<int:order_id>/unassign/<int:ou_id>")
def unassign_unit(order_id, ou_id):
    ou = OrderUnit.query.get_or_404(ou_id)
    if ou.order_id != order_id:
        abort(400)
    unit = ou.unit
    db.session.delete(ou)
    unit.status = "In Stock"
    unit.last_update = datetime.now(timezone.utc)
    db.session.commit()
    flash("Unassigned barcode.", "success")
    return redirect(url_for("orders") + f"#o{order_id}")



@app.post("/orders/<int:order_id>/delete")
def delete_order(order_id):
    o = db.session.get(Order, order_id)
    if not o:
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    # Unassign and delete all OrderUnit links
    ous = db.session.query(OrderUnit).filter_by(order_id=order_id).all()
    for ou in ous:
        if ou.unit:
            ou.unit.status = "In Stock"
            ou.unit.last_update = datetime.utcnow()
        db.session.delete(ou)
    # Delete related OrderItems if any (relationship on Order.items has delete-orphan cascade)
    try:
        db.session.delete(o)
        db.session.commit()
        flash(f"Order #{order_id} deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete order.", "error")
    return redirect(url_for("orders"))
@app.post("/api/ask_ai")
def ask_ai():
    """Enhanced AI endpoint using Life360AIService for comprehensive responses."""
    try:
        from ai_service import ai_service
        
        data = request.get_json(force=True, silent=True) or {}
        user_query = (data.get("prompt") or "").strip()
        
        if not user_query:
            return {"ok": False, "error": "Please provide a question or query."}
        
        # Process the query using our enhanced AI service
        result = ai_service.process_query(user_query)
        
        return result
        
    except ImportError:
        # Fallback to basic responses if AI service not available
        return {"ok": False, "error": "AI service not available. Please check configuration."}
    except Exception as e:
        app.logger.error(f"AI endpoint error: {e}")
        return {"ok": False, "error": f"Internal error: {str(e)}"}

@app.get("/api/ai_stats")
def ai_stats():
    """Get quick statistics for AI dashboard."""
    try:
        from ai_service import ai_service
        stats = ai_service.get_quick_stats()
        return {"ok": True, "stats": stats}
    except ImportError:
        return {"ok": False, "error": "AI service not available"}
    except Exception as e:
        app.logger.error(f"AI stats error: {e}")
        return {"ok": False, "error": f"Internal error: {str(e)}"}

@app.route("/ai-chat")
def ai_chat():
    """AI Chat interface page."""
    user = session.get("user")
    return render_template("ai_chat.html", user=user)

# ------------ Friendly template error (avoid opaque 500) ------------
@app.errorhandler(TemplateNotFound)
def _tmpl_missing(e):
    return (f"<h2>Template not found</h2><p>{e}</p>", 500)

# ------------------- Import-time DB init (works under Gunicorn/Azure) -------------------
# Initialize database tables on first request instead of at import time
@app.before_request
def init_db_once():
    """Initialize database on first request."""
    # Skip if already initialized
    if not hasattr(init_db_once, 'done'):
        try:
            # Ensure we're in an app context
            if not hasattr(app, 'app_context'):
                return
            _ensure_tables()
            if DEMO_MODE:
                try:
                    seed_demo_if_empty()
                    migrate_orders_to_db()
                except Exception as e:
                    app.logger.warning(f"Demo mode init failed: {e}")
            init_db_once.done = True
            app.logger.info("✓ Database initialized successfully")
        except Exception as _e:
            app.logger.error("DB init failed: %s", _e)
            # Don't fail the request if DB init fails, but log it
            init_db_once.done = True  # Mark as done to prevent repeated attempts

# --- Startup diagnostics (logs only) ---
def _startup_diag():
    try:
        from pathlib import Path as _P
        envp = _P(__file__).with_name(".env")
        present = bool(os.environ.get("AZURE_CLIENT_ID"))
        masked = (os.environ.get("AZURE_CLIENT_ID")[:8] + "..." + os.environ.get("AZURE_CLIENT_ID")[-6:]) if os.environ.get("AZURE_CLIENT_ID") else None
        app.logger.info("Auth diag: CLIENT_ID_present=%s SECRET_present=%s SECRET_source=%s ENV_exists=%s ENV_path=%s AUTHORITY=%s REDIRECT_PATH=%s",
                        present, bool(CLIENT_SECRET), globals().get("_CLIENT_SECRET_SRC","unknown"), envp.exists(), str(envp), AUTHORITY, REDIRECT_PATH)
    except Exception as e:
        app.logger.error("Startup diag failed: %s", e)

# ---------------- Courier Booking Routes ----------------

@app.route("/practitioners/<int:pid>/book-courier", methods=["GET", "POST"])
@app.route("/orders/<int:order_id>/book-courier", methods=["GET", "POST"])
def book_courier(pid=None, order_id=None):
    """Book courier service for a practitioner or order"""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    
    # Determine context (practitioner or order)
    practitioner = None
    order = None
    context = None
    
    if pid:
        practitioner = Practitioner.query.get(pid)
        if not practitioner:
            flash("Practitioner not found.", "error")
            return redirect(url_for("practitioners"))
        context = "practitioner"
    elif order_id:
        order = Order.query.get(order_id)
        if not order:
            flash("Order not found.", "error")
            return redirect(url_for("orders"))
        
        # Try to find practitioner by name, or create a temporary one
        practitioner = None
        if order.practitioner_name:
            practitioner = Practitioner.query.filter_by(
                first_name=order.practitioner_name.split()[0] if order.practitioner_name.split() else "",
                last_name=" ".join(order.practitioner_name.split()[1:]) if len(order.practitioner_name.split()) > 1 else ""
            ).first()
        
        # If no practitioner found, create a temporary one for the booking
        if not practitioner:
            practitioner = Practitioner(
                id=999999,  # Temporary ID
                first_name=order.name or "Unknown",
                last_name=order.surname or "Practitioner", 
                email=order.email if hasattr(order, 'email') else "",
                phone=order.phone if hasattr(order, 'phone') else "",
                provider=order.provider or "Unknown"
            )
        
        context = "order"
    
    if request.method == "POST":
        try:
            # Get form data - Shipment Details
            custom_tracking_ref = request.form.get('custom_tracking_ref', '').strip()
            customer_reference = request.form.get('customer_reference', '').strip()
            
            # Collection Details
            collection_date = request.form.get('collection_date', '').strip()
            collection_time = request.form.get('collection_time', '').strip()
            collection_type = request.form.get('collection_type', 'residential')
            collection_address = request.form.get('collection_address', '').strip()
            collection_building = request.form.get('collection_building', '').strip()
            collection_street = request.form.get('collection_street', '').strip()
            collection_suburb = request.form.get('collection_suburb', '').strip()
            collection_city = request.form.get('collection_city', '').strip()
            collection_province = request.form.get('collection_province', '').strip()
            collection_postal_code = request.form.get('collection_postal_code', '').strip()
            collection_instructions = request.form.get('collection_instructions', '').strip()
            collection_contact_name = request.form.get('collection_contact_name', '').strip()
            collection_email = request.form.get('collection_email', '').strip()
            collection_country_code = request.form.get('collection_country_code', '+27')
            collection_mobile = request.form.get('collection_mobile', '').strip()
            
            # Delivery Details
            delivery_date = request.form.get('delivery_date', '').strip()
            delivery_type = request.form.get('delivery_type', 'residential')
            delivery_address = request.form.get('delivery_address', '').strip()
            delivery_building = request.form.get('delivery_building', '').strip()
            delivery_street = request.form.get('delivery_street', '').strip()
            delivery_suburb = request.form.get('delivery_suburb', '').strip()
            delivery_city = request.form.get('delivery_city', '').strip()
            delivery_province = request.form.get('delivery_province', '').strip()
            delivery_postal_code = request.form.get('delivery_postal_code', '').strip()
            delivery_instructions = request.form.get('delivery_instructions', '').strip()
            delivery_contact_name = request.form.get('delivery_contact_name', '').strip()
            delivery_email = request.form.get('delivery_email', '').strip()
            delivery_country_code = request.form.get('delivery_country_code', '+27')
            delivery_mobile = request.form.get('delivery_mobile', '').strip()
            
            # Parcel Details
            parcel_type = request.form.get('parcel_type', 'custom')
            parcel_length = float(request.form.get('parcel_length', 0))
            parcel_width = float(request.form.get('parcel_width', 0))
            parcel_height = float(request.form.get('parcel_height', 0))
            parcel_weight = float(request.form.get('parcel_weight', 1.0))
            
            # Service Details
            service_type = request.form.get('service_type', 'LOF')
            
            # Provider Details
            provider = request.form.get('courier_provider', 'courier_guy_geneway')
            
            # Validate required fields based on Shiplogic API requirements
            required_collection_fields = {
                'collection_date': collection_date,
                'collection_time': collection_time,
                'collection_street': collection_street,
                'collection_suburb': collection_suburb,
                'collection_city': collection_city,
                'collection_province': collection_province,
                'collection_postal_code': collection_postal_code,
                'collection_contact_name': collection_contact_name,
                'collection_mobile': collection_mobile
            }
            
            required_delivery_fields = {
                'delivery_date': delivery_date,
                'delivery_street': delivery_street,
                'delivery_suburb': delivery_suburb,
                'delivery_city': delivery_city,
                'delivery_province': delivery_province,
                'delivery_postal_code': delivery_postal_code,
                'delivery_contact_name': delivery_contact_name,
                'delivery_mobile': delivery_mobile
            }
            
            # Check for missing fields and provide specific error messages
            missing_fields = []
            for field_name, field_value in required_collection_fields.items():
                if not field_value or field_value.strip() == '':
                    missing_fields.append(f"Collection {field_name.replace('_', ' ').title()}")
            
            for field_name, field_value in required_delivery_fields.items():
                if not field_value or field_value.strip() == '':
                    missing_fields.append(f"Delivery {field_name.replace('_', ' ').title()}")
            
            if missing_fields:
                error_message = f"Please fill in the following required fields: {', '.join(missing_fields)}"
                flash(error_message, "error")
                if context == "order":
                    return redirect(url_for("book_courier", order_id=order_id))
                else:
                    return redirect(url_for("book_courier", pid=pid))
            
            # Build addresses
            pickup_address = f"{collection_street}, {collection_suburb}, {collection_city}, {collection_province} {collection_postal_code}"
            if collection_building:
                pickup_address = f"{collection_building}, {pickup_address}"
            
            delivery_address = f"{delivery_street}, {delivery_suburb}, {delivery_city}, {delivery_province} {delivery_postal_code}"
            if delivery_building:
                delivery_address = f"{delivery_building}, {delivery_address}"
            
            # Get pricing from API
            from shiplogic_service import ShiplogicService, get_demo_pricing
            
            shiplogic = ShiplogicService(provider=provider)
            if shiplogic.api_key:
                pricing_result = shiplogic.get_service_pricing(pickup_address, delivery_address, parcel_weight, 
                                                             parcel_length, parcel_width, parcel_height, 
                                                             None, service_type)
            else:
                pricing_result = get_demo_pricing(pickup_address, delivery_address, parcel_weight, 
                                                parcel_length, parcel_width, parcel_height, 
                                                None, service_type)
            
            service_cost = 0.0
            if pricing_result['success']:
                service_cost = pricing_result['pricing'].get(service_type, 0.0)
            
            # Prepare booking data according to Shiplogic API format (from Postman collection)
            booking_data = {
                'collection_address': {
                    'type': collection_type,
                    'company': collection_building or '',
                    'street_address': collection_street,
                    'local_area': collection_suburb,
                    'city': collection_city,
                    'zone': collection_province,
                    'country': 'ZA',
                    'code': collection_postal_code
                },
                'collection_contact': {
                    'name': collection_contact_name,
                    'mobile_number': f"{collection_country_code}{collection_mobile}",
                    'email': collection_email
                },
                'delivery_address': {
                    'type': delivery_type,
                    'company': delivery_building or '',
                    'street_address': delivery_street,
                    'local_area': delivery_suburb,
                    'city': delivery_city,
                    'zone': delivery_province,
                    'country': 'ZA',
                    'code': delivery_postal_code
                },
                'delivery_contact': {
                    'name': delivery_contact_name,
                    'mobile_number': f"{delivery_country_code}{delivery_mobile}",
                    'email': delivery_email
                },
                'parcels': [{
                    'parcel_description': f"{parcel_type.title()} parcel - {custom_tracking_ref or customer_reference}",
                    'submitted_length_cm': parcel_length,
                    'submitted_width_cm': parcel_width,
                    'submitted_height_cm': parcel_height,
                    'submitted_weight_kg': parcel_weight
                }],
                'special_instructions_collection': collection_instructions,
                'special_instructions_delivery': delivery_instructions,
                'declared_value': 0,
                'collection_min_date': f"{collection_date}T00:00:00.000Z",
                'collection_after': collection_time.split(':')[0] + ':00',
                'collection_before': str(int(collection_time.split(':')[0]) + 8) + ':00',
                'delivery_min_date': f"{delivery_date}T00:00:00.000Z",
                'delivery_after': '08:00',
                'delivery_before': '17:00',
                'custom_tracking_reference': custom_tracking_ref,
                'customer_reference': customer_reference,
                'service_level_code': service_type,
                'mute_notifications': False
            }
            
            # Import and use Shiplogic service
            from shiplogic_service import ShiplogicService, create_demo_booking
            
            # Check if we have API key (demo mode if not). Use the selected provider
            shiplogic = ShiplogicService(provider=provider)
            if shiplogic.api_key:
                result = shiplogic.create_courier_booking(booking_data)
            else:
                result = create_demo_booking(booking_data)
            
            # Determine if client expects JSON (fetch-based submission)
            expects_json = ('application/json' in (request.headers.get('Accept') or '')) or (request.headers.get('X-Requested-With') in ('fetch', 'XMLHttpRequest'))

            if result['success']:
                # Handle temporary practitioner case
                practitioner_id = practitioner.id
                if practitioner.id == 999999:  # Temporary practitioner
                    # Create a real practitioner entry for the booking
                    new_practitioner = Practitioner(
                        first_name=practitioner.first_name,
                        last_name=practitioner.last_name,
                        email=practitioner.email,
                        phone=practitioner.phone,
                        provider=practitioner.provider
                    )
                    db.session.add(new_practitioner)
                    db.session.flush()  # Get the new ID
                    practitioner_id = new_practitioner.id
                
                # Generate waybill data
                waybill_data = {
                    'booking_id': result['booking_id'],
                    'tracking_number': result['tracking_number'],
                    'service_type': service_type,
                    'pickup_address': pickup_address,
                    'delivery_address': delivery_address,
                    'recipient_name': delivery_contact_name,
                    'recipient_phone': f"{delivery_country_code}{delivery_mobile}",
                    'package_description': booking_data['parcels'][0].get('parcel_description'),
                    'package_weight': parcel_weight,
                    'collection_date': collection_date,
                    'collection_time': collection_time,
                    'delivery_date': delivery_date,
                    'cost': service_cost or result.get('cost', 0.0),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                # Save to database
                courier_booking = CourierBooking(
                    practitioner_id=practitioner_id,
                    shiplogic_booking_id=result['booking_id'],
                    tracking_number=result['tracking_number'],
                    provider=provider,
                    pickup_address=pickup_address,
                    delivery_address=delivery_address,
                    recipient_name=delivery_contact_name,
                    recipient_phone=f"{delivery_country_code}{delivery_mobile}",
                    package_description=booking_data['package_description'],
                    package_weight=parcel_weight,
                    package_value=0.0,  # Not used in new form
                    special_instructions=f"Service: {service_type}. Collection: {collection_instructions}. Delivery: {delivery_instructions}",
                    service_type=service_type,
                    service_cost=service_cost,
                    waybill_data=json.dumps(waybill_data),
                    waybill_generated=True,
                    status='confirmed',
                    estimated_delivery=datetime.fromisoformat(result['estimated_delivery'].replace('Z', '+00:00')) if result.get('estimated_delivery') else None,
                    cost=service_cost or result.get('cost', 0.0)
                )
                
                db.session.add(courier_booking)
                db.session.commit()
                
                if expects_json:
                    return jsonify({
                        "success": True,
                        "tracking_number": result['tracking_number'],
                        "booking_id": courier_booking.id,
                        "redirect_url": url_for("courier_bookings")
                    })
                
                flash(f"Courier booking successful! Tracking number: {result['tracking_number']}", "success")
                
                # Redirect based on context
                if context == "order":
                    return redirect(url_for("orders"))
                else:
                    return redirect(url_for("practitioners"))
            else:
                if expects_json:
                    return jsonify({"success": False, "error": result['error']}), 400
                
                flash(f"Failed to book courier: {result['error']}", "error")
                if context == "order":
                    return redirect(url_for("book_courier", order_id=order_id))
                else:
                    return redirect(url_for("book_courier", pid=pid))
                
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Courier booking error: {e}")
            expects_json = ('application/json' in (request.headers.get('Accept') or '')) or (request.headers.get('X-Requested-With') in ('fetch', 'XMLHttpRequest'))
            if expects_json:
                return jsonify({"success": False, "error": "An error occurred while booking courier service."}), 500
            flash("An error occurred while booking courier service.", "error")
            if context == "order":
                return redirect(url_for("book_courier", order_id=order_id))
            else:
                return redirect(url_for("book_courier", pid=pid))
    
    # GET request - show booking form
    # Get provider from URL parameter if provided
    selected_provider = request.args.get('provider', 'courier_guy_geneway')
    
    return render_template("courier_booking.html", 
                         user=user, 
                         practitioner=practitioner,
                         order=order,
                         context=context,
                         selected_provider=selected_provider)

@app.route("/courier-bookings")
def courier_bookings():
    """View all courier bookings"""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    
    bookings = CourierBooking.query.order_by(CourierBooking.created_at.desc()).all()
    return render_template("courier_bookings.html", 
                         user=user, 
                         bookings=bookings)

@app.route("/courier-bookings/<int:booking_id>/status")
def courier_booking_status(booking_id):
    """Get courier booking status"""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    booking = CourierBooking.query.get(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    
    # Import and use Shiplogic service
    from shiplogic_service import ShiplogicService, get_demo_status
    
    shiplogic = ShiplogicService()
    if shiplogic.api_key:
        result = shiplogic.get_booking_status(booking.shiplogic_booking_id)
    else:
        result = get_demo_status(booking.shiplogic_booking_id)
    
    if result['success']:
        # Update local database
        booking.status = result['status']
        booking.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "status": result['status'],
            "tracking_number": result['tracking_number'],
            "current_location": result.get('current_location'),
            "estimated_delivery": result.get('estimated_delivery'),
            "updates": result.get('updates', [])
        })
    else:
        return jsonify({"error": result['error']}), 500

@app.route("/courier-bookings/<int:booking_id>/waybill")
def courier_booking_waybill(booking_id):
    """Get courier booking waybill details"""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    booking = CourierBooking.query.get(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    
    if not booking.waybill_generated or not booking.waybill_data:
        return jsonify({"error": "Waybill not available"}), 404
    
    try:
        waybill_data = json.loads(booking.waybill_data)
        return jsonify({
            "success": True,
            "booking_id": booking.id,
            "status": booking.status,
            "waybill_data": waybill_data
        })
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid waybill data"}), 500

@app.route("/api/courier-pricing", methods=["POST"])
def get_courier_pricing():
    """Get pricing for courier services from The Courier Guy API"""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json()
        pickup_address = data.get('pickup_address', '').strip()
        delivery_address = data.get('delivery_address', '').strip()
        parcel_weight = float(data.get('parcel_weight', 1.0))
        parcel_length = float(data.get('parcel_length', 0))
        parcel_width = float(data.get('parcel_width', 0))
        parcel_height = float(data.get('parcel_height', 0))
        parcel_type = data.get('parcel_type', None)
        service_type = data.get('service_type', None)
        provider = data.get('provider', 'courier_guy_geneway')
        
        if not pickup_address or not delivery_address:
            return jsonify({"error": "Pickup and delivery addresses are required"}), 400
        
        from shiplogic_service import ShiplogicService, get_demo_pricing
        
        shiplogic = ShiplogicService(provider=provider)
        result = shiplogic.get_service_pricing(pickup_address, delivery_address, parcel_weight, 
                                             parcel_length, parcel_width, parcel_height, 
                                             parcel_type, service_type)
        app.logger.info(f"API result: success={result.get('success')}, error={result.get('error')}")
        
        if result['success']:
            return jsonify({
                "success": True,
                "services": result['services'],
                "pricing": result['pricing'],
                "data": result['data']
            })
        else:
            return jsonify({"error": result['error']}), 500
            
    except Exception as e:
        app.logger.error(f"Pricing API error: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Azure-compatible WooCommerce sync endpoints
@app.route('/api/woocommerce/sync', methods=['POST'])
def api_sync_woocommerce():
    """API endpoint to trigger WooCommerce sync - Azure compatible"""
    try:
        from woocommerce_integration import sync_woocommerce_orders
        
        # Get optional parameters
        data = request.get_json() or {}
        days_back = data.get('days_back', 0.042)  # Default: 1 hour
        
        # Perform sync
        result = sync_woocommerce_orders(days_back=days_back)
        
        return jsonify({
            'success': result['success'],
            'message': f"Synced {result.get('new_orders', 0)} new orders, updated {result.get('updated_orders', 0)} orders",
            'new_orders': result.get('new_orders', 0),
            'updated_orders': result.get('updated_orders', 0),
            'total_synced': result.get('total_synced', 0),
            'timestamp': datetime.utcnow().isoformat()
        }), 200 if result['success'] else 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/api/woocommerce/status', methods=['GET'])
def api_woocommerce_status():
    """Get WooCommerce sync status"""
    try:
        # Get WooCommerce orders count
        wc_orders = Order.query.filter(Order.woocommerce_id.isnot(None)).all()
        recent_orders = [o for o in wc_orders if o.ordered_at and o.ordered_at > datetime.utcnow() - timedelta(hours=24)]
        
        return jsonify({
            'success': True,
            'total_woocommerce_orders': len(wc_orders),
            'orders_last_24h': len(recent_orders),
            'latest_order': {
                'id': wc_orders[0].woocommerce_id,
                'customer': wc_orders[0].customer_name,
                'total': wc_orders[0].total_amount,
                'date': wc_orders[0].ordered_at.isoformat() if wc_orders[0].ordered_at else None
            } if wc_orders else None,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Azure-compatible Fillout sync endpoints
@app.route('/api/fillout/sync', methods=['POST'])
def api_sync_fillout():
    """API endpoint to trigger Fillout sync - Azure compatible"""
    try:
        from fillout_integration import sync_fillout_submissions
        
        # Get optional parameters
        data = request.get_json() or {}
        hours_back = data.get('hours_back', 24)  # Default: 24 hours
        
        # Perform sync
        result = sync_fillout_submissions(hours_back=hours_back)
        
        return jsonify({
            'success': result['success'],
            'message': f"Synced {result.get('new_orders', 0)} new submissions, updated {result.get('updated_orders', 0)} submissions",
            'new_orders': result.get('new_orders', 0),
            'updated_orders': result.get('updated_orders', 0),
            'total_synced': result.get('total_synced', 0),
            'timestamp': datetime.utcnow().isoformat()
        }), 200 if result['success'] else 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/api/fillout/status', methods=['GET'])
def api_fillout_status():
    """Get Fillout sync status"""
    try:
        # Get Fillout submissions count
        fillout_orders = Order.query.filter(Order.fillout_submission_id.isnot(None)).all()
        recent_orders = [o for o in fillout_orders if o.ordered_at and o.ordered_at > datetime.utcnow() - timedelta(hours=24)]
        
        return jsonify({
            'success': True,
            'total_fillout_submissions': len(fillout_orders),
            'submissions_last_24h': len(recent_orders),
            'latest_submission': {
                'id': fillout_orders[0].fillout_submission_id,
                'customer': fillout_orders[0].customer_name,
                'service': fillout_orders[0].items_description,
                'date': fillout_orders[0].ordered_at.isoformat() if fillout_orders[0].ordered_at else None
            } if fillout_orders else None,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("PORT", "5000"))
    logging.info("Starting Life360 app on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG","0") in ("1","true","yes","on"))

@app.get("/auth/diagnostics")
def auth_diagnostics():
    from pathlib import Path as _P
    envp = _P(__file__).with_name(".env")
    return jsonify({
        "ok": True,
        "AZURE_CLIENT_ID_present": bool(os.environ.get("AZURE_CLIENT_ID")),
        "secret_source": globals().get("_CLIENT_SECRET_SRC", "unknown"),
        "has_secret_env_or_file": bool(os.environ.get("AZURE_CLIENT_SECRET") or CLIENT_SECRET),
        "AUTHORITY": AUTHORITY,
        "TENANT_ID": TENANT_ID,
        "supported_hint": "Set AZURE_AUTHORITY to /common for MSA+Work or /organizations for Work only",
        "REDIRECT_PATH": REDIRECT_PATH,
        "ENV_path": str(envp),
        "ENV_exists": envp.exists(),
        "redirect_uri": (request.url_root.rstrip("/") + REDIRECT_PATH) if request else None
    })

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24  # 24 hours

@app.get("/auth/whoami")
def auth_whoami():
    tok = session.get("ms_access_token")
    if not tok:
        return jsonify({"ok": False, "error": "no_access_token"}), 401
    try:
        resp = requests.get("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {tok}"})
        return jsonify({"ok": resp.ok, "status": resp.status_code, "data": resp.json() if resp.content else None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
@app.route("/practitioners/<int:pid>/edit", methods=["GET", "POST"])
def practitioners_edit(pid):
    try:
        p = Practitioner.query.get(pid)
        if not p:
            flash("Practitioner not found.", "error")
            return redirect(url_for("practitioners"))
        
        if request.method == "GET":
            # Show edit page
            return render_template("practitioner_edit.html", practitioner=p)
        
        # Handle POST request (form submission)
        p.provider   = normalize_provider(request.form.get("provider") or "")
        p.title      = (request.form.get("title") or "").strip()
        p.first_name = (request.form.get("first_name") or "").strip()
        p.last_name  = (request.form.get("last_name") or "").strip()
        p.email      = (request.form.get("email") or "").strip()
        p.phone      = (request.form.get("phone") or "").strip()
        p.notes      = (request.form.get("notes") or "").strip()
        db.session.commit()
        flash("Practitioner updated successfully!", "success")
        return redirect(url_for("practitioners"))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to update practitioner {pid}: {e}")
        flash("Failed to update practitioner.", "error")
    return redirect(url_for("practitioners"))
