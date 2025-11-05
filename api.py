"""
RESTful API endpoints for Life360 application.
"""
from typing import Dict, List, Optional, Any
from flask import Blueprint, request, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import jwt
from datetime import datetime, timedelta
from security import SecurityValidator, InputValidator, rate_limiter
from error_handling import log_user_action, log_security_event, ValidationError, BusinessLogicError


def create_api_blueprint(db: SQLAlchemy) -> Blueprint:
    """Create API blueprint with all endpoints."""
    
    api = Blueprint('api', __name__, url_prefix='/api/v1')
    
    def require_auth(f):
        """Decorator to require API authentication."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return jsonify({'error': 'Missing authorization token'}), 401
            
            try:
                if token.startswith('Bearer '):
                    token = token[7:]
                
                # Verify JWT token
                payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
                user_id = payload.get('user_id')
                
                if not user_id:
                    return jsonify({'error': 'Invalid token'}), 401
                
                # Add user info to request context
                request.current_user = {'id': user_id, 'email': payload.get('email')}
                
            except jwt.ExpiredSignatureError:
                return jsonify({'error': 'Token expired'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'error': 'Invalid token'}), 401
            
            return f(*args, **kwargs)
        return decorated_function
    
    def rate_limit(limit: int = 100, window: int = 3600):
        """Decorator for rate limiting."""
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                client_id = request.remote_addr
                if not rate_limiter.is_allowed(client_id, limit, window):
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                return f(*args, **kwargs)
            return decorated_function
        return decorator
    
    @api.route('/auth/login', methods=['POST'])
    @rate_limit(limit=10, window=3600)  # 10 attempts per hour
    def api_login():
        """API login endpoint."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'JSON data required'}), 400
            
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not email or not password:
                return jsonify({'error': 'Email and password required'}), 400
            
            # Validate email format
            if not SecurityValidator.validate_email(email):
                return jsonify({'error': 'Invalid email format'}), 400
            
            # TODO: Implement actual authentication logic
            # For now, return a mock response
            if email == 'admin@life360.com' and password == 'admin123':
                # Generate JWT token
                payload = {
                    'user_id': 'admin',
                    'email': email,
                    'exp': datetime.utcnow() + timedelta(hours=24)
                }
                token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
                
                log_user_action('admin', 'api_login', {'email': email})
                
                return jsonify({
                    'token': token,
                    'user': {
                        'id': 'admin',
                        'email': email,
                        'name': 'Administrator'
                    }
                })
            else:
                log_security_event('failed_api_login', {'email': email})
                return jsonify({'error': 'Invalid credentials'}), 401
                
        except Exception as e:
            current_app.logger.error(f"API login error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/orders', methods=['GET'])
    @require_auth
    @rate_limit()
    def get_orders():
        """Get all orders."""
        try:
            from app import Order, OrderItem
            
            # Get query parameters
            page = int(request.args.get('page', 1))
            per_page = min(int(request.args.get('per_page', 20)), 100)
            provider = request.args.get('provider')
            status = request.args.get('status')
            
            # Build query
            query = Order.query
            
            if provider:
                query = query.filter(Order.provider == provider)
            if status:
                query = query.filter(Order.status == status)
            
            # Paginate results
            orders = query.order_by(Order.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            # Format response
            orders_data = []
            for order in orders.items:
                orders_data.append({
                    'id': order.id,
                    'provider': order.provider,
                    'name': order.name,
                    'surname': order.surname,
                    'practitioner_name': order.practitioner_name,
                    'status': order.status,
                    'ordered_at': order.ordered_at.isoformat() if order.ordered_at else None,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'completed_at': order.completed_at.isoformat() if order.completed_at else None,
                    'notes': order.notes,
                    'items': [{'sku': item.sku, 'qty': item.qty} for item in order.items],
                    'workflow': {
                        'sent_out': order.sent_out,
                        'received_back': order.received_back,
                        'kit_registered': order.kit_registered,
                        'results_sent': order.results_sent,
                        'paid': order.paid,
                        'invoiced': order.invoiced
                    }
                })
            
            return jsonify({
                'orders': orders_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': orders.total,
                    'pages': orders.pages,
                    'has_next': orders.has_next,
                    'has_prev': orders.has_prev
                }
            })
            
        except Exception as e:
            current_app.logger.error(f"API get orders error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/orders', methods=['POST'])
    @require_auth
    @rate_limit()
    def create_order():
        """Create a new order."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'JSON data required'}), 400
            
            # Validate input
            is_valid, errors = InputValidator.validate_order_data(data)
            if not is_valid:
                return jsonify({'error': 'Validation failed', 'details': errors}), 400
            
            from app import Order, OrderItem
            
            # Create order
            order = Order(
                provider=SecurityValidator.normalize_provider(data['provider']),
                name=data['name'].strip(),
                surname=data['surname'].strip(),
                practitioner_name=data.get('practitioner_name', '').strip() or None,
                notes=data.get('notes', '').strip() or None,
                status=data.get('status', 'Pending'),
                ordered_at=datetime.fromisoformat(data['ordered_at']) if data.get('ordered_at') else datetime.utcnow()
            )
            
            db.session.add(order)
            db.session.flush()  # Get the ID
            
            # Add order items
            for i in range(1, 4):
                sku = data.get(f'item_sku_{i}', '').strip()
                qty = data.get(f'item_qty_{i}', '')
                
                if sku and qty:
                    try:
                        qty_int = int(qty)
                        db.session.add(OrderItem(
                            order_id=order.id,
                            sku=sku,
                            qty=qty_int
                        ))
                    except ValueError:
                        pass  # Skip invalid quantities
            
            db.session.commit()
            
            log_user_action(request.current_user['id'], 'create_order', {'order_id': order.id})
            
            return jsonify({
                'message': 'Order created successfully',
                'order_id': order.id
            }), 201
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"API create order error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/orders/<int:order_id>', methods=['GET'])
    @require_auth
    @rate_limit()
    def get_order(order_id):
        """Get a specific order."""
        try:
            from app import Order
            
            order = Order.query.get_or_404(order_id)
            
            order_data = {
                'id': order.id,
                'provider': order.provider,
                'name': order.name,
                'surname': order.surname,
                'practitioner_name': order.practitioner_name,
                'status': order.status,
                'ordered_at': order.ordered_at.isoformat() if order.ordered_at else None,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'completed_at': order.completed_at.isoformat() if order.completed_at else None,
                'notes': order.notes,
                'items': [{'sku': item.sku, 'qty': item.qty} for item in order.items],
                'workflow': {
                    'sent_out': order.sent_out,
                    'received_back': order.received_back,
                    'kit_registered': order.kit_registered,
                    'results_sent': order.results_sent,
                    'paid': order.paid,
                    'invoiced': order.invoiced
                }
            }
            
            return jsonify(order_data)
            
        except Exception as e:
            current_app.logger.error(f"API get order error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/orders/<int:order_id>', methods=['PUT'])
    @require_auth
    @rate_limit()
    def update_order(order_id):
        """Update an order."""
        try:
            from app import Order
            
            order = Order.query.get_or_404(order_id)
            data = request.get_json()
            
            if not data:
                return jsonify({'error': 'JSON data required'}), 400
            
            # Update fields
            if 'name' in data:
                order.name = data['name'].strip()
            if 'surname' in data:
                order.surname = data['surname'].strip()
            if 'practitioner_name' in data:
                order.practitioner_name = data['practitioner_name'].strip() or None
            if 'status' in data:
                order.status = data['status']
            if 'notes' in data:
                order.notes = data['notes'].strip() or None
            
            # Update workflow flags
            if 'workflow' in data:
                workflow = data['workflow']
                order.sent_out = workflow.get('sent_out', order.sent_out)
                order.received_back = workflow.get('received_back', order.received_back)
                order.kit_registered = workflow.get('kit_registered', order.kit_registered)
                order.results_sent = workflow.get('results_sent', order.results_sent)
                order.paid = workflow.get('paid', order.paid)
                order.invoiced = workflow.get('invoiced', order.invoiced)
            
            db.session.commit()
            
            log_user_action(request.current_user['id'], 'update_order', {'order_id': order_id})
            
            return jsonify({'message': 'Order updated successfully'})
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"API update order error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/practitioners', methods=['GET'])
    @require_auth
    @rate_limit()
    def get_practitioners():
        """Get all practitioners."""
        try:
            from app import Practitioner, PractitionerFlag
            
            # Get query parameters
            page = int(request.args.get('page', 1))
            per_page = min(int(request.args.get('per_page', 20)), 100)
            provider = request.args.get('provider')
            onboarded = request.args.get('onboarded')
            
            # Build query
            query = Practitioner.query
            
            if provider:
                query = query.filter(Practitioner.provider == provider)
            
            # Paginate results
            practitioners = query.order_by(Practitioner.last_name, Practitioner.first_name).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            # Get flags
            flags = {f.pid: f for f in PractitionerFlag.query.all()}
            
            # Format response
            practitioners_data = []
            for practitioner in practitioners.items:
                flag = flags.get(practitioner.id)
                
                practitioner_data = {
                    'id': practitioner.id,
                    'provider': practitioner.provider,
                    'title': practitioner.title,
                    'first_name': practitioner.first_name,
                    'last_name': practitioner.last_name,
                    'email': practitioner.email,
                    'phone': practitioner.phone,
                    'notes': practitioner.notes,
                    'created_at': practitioner.created_at.isoformat() if practitioner.created_at else None,
                    'flags': {
                        'training': bool(flag.training) if flag else False,
                        'website': bool(flag.website) if flag else False,
                        'whatsapp': bool(flag.whatsapp) if flag else False,
                        'engagebay': bool(flag.engagebay) if flag else False,
                        'onboarded': bool(flag.onboarded) if flag else False
                    }
                }
                
                # Filter by onboarded status if requested
                if onboarded is not None:
                    is_onboarded = practitioner_data['flags']['onboarded']
                    if onboarded.lower() == 'true' and not is_onboarded:
                        continue
                    elif onboarded.lower() == 'false' and is_onboarded:
                        continue
                
                practitioners_data.append(practitioner_data)
            
            return jsonify({
                'practitioners': practitioners_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': practitioners.total,
                    'pages': practitioners.pages,
                    'has_next': practitioners.has_next,
                    'has_prev': practitioners.has_prev
                }
            })
            
        except Exception as e:
            current_app.logger.error(f"API get practitioners error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/stock', methods=['GET'])
    @require_auth
    @rate_limit()
    def get_stock():
        """Get stock inventory."""
        try:
            from app import StockItem, StockUnit
            from sqlalchemy import func
            
            # Get query parameters
            provider = request.args.get('provider')
            low_stock = request.args.get('low_stock', 'false').lower() == 'true'
            
            # Build query
            query = StockItem.query
            
            if provider:
                query = query.filter(StockItem.provider == provider)
            
            items = query.order_by(StockItem.name).all()
            
            # Format response
            stock_data = []
            for item in items:
                # Get stock counts
                total_units = db.session.query(func.count(StockUnit.id)).filter(
                    StockUnit.item_id == item.id
                ).scalar() or 0
                
                in_stock = db.session.query(func.count(StockUnit.id)).filter(
                    StockUnit.item_id == item.id,
                    StockUnit.status == "In Stock"
                ).scalar() or 0
                
                # Skip if low stock filter is enabled and item has sufficient stock
                if low_stock and in_stock > 2:
                    continue
                
                stock_data.append({
                    'id': item.id,
                    'name': item.name,
                    'provider': item.provider,
                    'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
                    'received_date': item.received_date.isoformat() if item.received_date else None,
                    'code_type': item.code_type,
                    'total_units': total_units,
                    'in_stock': in_stock,
                    'assigned': total_units - in_stock
                })
            
            return jsonify({'stock': stock_data})
            
        except Exception as e:
            current_app.logger.error(f"API get stock error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api.route('/dashboard/stats', methods=['GET'])
    @require_auth
    @rate_limit()
    def get_dashboard_stats():
        """Get dashboard statistics."""
        try:
            from app import Order, Practitioner, PractitionerFlag
            from sqlalchemy import func
            
            # Get order statistics
            total_orders = Order.query.count()
            completed_orders = Order.query.filter(Order.status.ilike("%completed%")).count()
            cancelled_orders = Order.query.filter(Order.status.ilike("%cancel%")).count()
            pending_orders = total_orders - completed_orders - cancelled_orders
            
            # Get practitioner statistics
            total_practitioners = Practitioner.query.count()
            onboarded_practitioners = PractitionerFlag.query.filter_by(onboarded=True).count()
            pending_practitioners = total_practitioners - onboarded_practitioners
            
            # Get provider distribution
            provider_stats = db.session.query(
                Order.provider,
                func.count(Order.id).label('count')
            ).group_by(Order.provider).all()
            
            providers = [{'name': stat.provider, 'count': stat.count} for stat in provider_stats]
            
            return jsonify({
                'orders': {
                    'total': total_orders,
                    'completed': completed_orders,
                    'pending': pending_orders,
                    'cancelled': cancelled_orders
                },
                'practitioners': {
                    'total': total_practitioners,
                    'onboarded': onboarded_practitioners,
                    'pending': pending_practitioners
                },
                'providers': providers
            })
            
        except Exception as e:
            current_app.logger.error(f"API get dashboard stats error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    return api



