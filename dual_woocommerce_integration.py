#!/usr/bin/env python3
"""
Dual WooCommerce Integration for both Geneway and Optiway
Handles orders from both stores with correct provider assignment
"""
import requests
from requests.auth import HTTPBasicAuth
import json
from datetime import datetime, timedelta
from app import app, db, Order
import logging

# Geneway WooCommerce Configuration
GENEWAY_CONFIG = {
    'base_url': 'https://geneway.co.za',
    'consumer_key': 'ck_ce467c6d4f0b3d980124440c6b28fb26faa06817',
    'consumer_secret': 'cs_05d08a784db62bd25f2346c8e02dd01ae8ba33de',
    'api_version': 'wc/v3',
    'provider_name': 'Geneway'
}

# Optiway WooCommerce Configuration  
OPTIWAY_CONFIG = {
    'base_url': 'https://optiway.co.za',
    'consumer_key': 'ck_11a1eb1607dadd389ca725d644ea6f157ae019a7',
    'consumer_secret': 'cs_d8dffa7dd331a8d2540bf31ece17c4a8c90b0cae',
    'api_version': 'wc/v3',
    'provider_name': 'Optiway'
}

class DualWooCommerceAPI:
    """WooCommerce API client that can handle both Geneway and Optiway"""
    
    def __init__(self, config):
        self.config = config
        self.base_url = f"{config['base_url']}/wp-json/{config['api_version']}"
        self.auth = HTTPBasicAuth(config['consumer_key'], config['consumer_secret'])
        self.session = requests.Session()
        self.session.auth = self.auth
        self.provider_name = config['provider_name']
    
    def get_orders(self, status='any', per_page=100, page=1, after=None):
        """Get orders from WooCommerce store"""
        url = f"{self.base_url}/orders"
        params = {
            'status': status,
            'per_page': per_page,
            'page': page,
            'orderby': 'date',
            'order': 'desc'
        }
        
        if after:
            params['after'] = after.isoformat()
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"{self.provider_name} API error: {e}")
            return []

def map_woocommerce_to_local_order(wc_order, provider_name):
    """Map WooCommerce order data to local Order model format"""
    import json
    
    # Store the complete raw API response
    raw_api_data = json.dumps(wc_order, indent=2, default=str)
    
    # Extract customer information
    billing = wc_order.get('billing', {})
    shipping = wc_order.get('shipping', {})
    
    # Use shipping address if available, otherwise billing
    customer_name = f"{shipping.get('first_name', billing.get('first_name', ''))} {shipping.get('last_name', billing.get('last_name', ''))}"
    customer_email = billing.get('email', '')
    customer_phone = billing.get('phone', shipping.get('phone', ''))

    # Format address
    address_parts = [
        shipping.get('address_1', billing.get('address_1', '')),
        shipping.get('address_2', billing.get('address_2', '')),
        shipping.get('city', billing.get('city', '')),
        shipping.get('state', billing.get('state', '')),
        shipping.get('postcode', billing.get('postcode', '')),
        shipping.get('country', billing.get('country', ''))
    ]
    address = ', '.join([part for part in address_parts if part])
    
    # Map all WooCommerce orders to Pending status as requested
    status_mapping = {
        'pending': 'Pending',
        'processing': 'Pending',
        'on-hold': 'Pending',
        'completed': 'Pending',
        'cancelled': 'Pending',
        'refunded': 'Pending',
        'failed': 'Pending'
    }
    
    # Extract line items
    items = []
    for item in wc_order.get('line_items', []):
        items.append(f"{item.get('name', 'Unknown')} (Qty: {item.get('quantity', 1)})")
    
    return {
        'woocommerce_id': wc_order.get('id'),
        'customer_name': customer_name.strip(),
        'customer_email': customer_email,
        'customer_phone': customer_phone,
        'address': address,
        'items_description': ' | '.join(items),
        'total_amount': float(wc_order.get('total', 0)),
        'status': status_mapping.get(wc_order.get('status', 'pending'), 'Pending'),
        'order_date': datetime.fromisoformat(wc_order.get('date_created', '').replace('Z', '+00:00')),
        'notes': wc_order.get('customer_note', ''),
        'payment_method': wc_order.get('payment_method_title', ''),
        'provider': provider_name,  # Use the provider name from config
        'ordered_at': datetime.fromisoformat(wc_order.get('date_created', '').replace('Z', '+00:00')),
        'name': billing.get('first_name', ''),
        'surname': billing.get('last_name', ''),
        'raw_api_data': raw_api_data
    }

def sync_both_woocommerce_stores(days_back=3):
    """Sync orders from both Geneway and Optiway stores"""
    
    with app.app_context():
        total_synced = 0
        new_orders = 0
        updated_orders = 0
        
        # Calculate the date to sync from
        sync_from = datetime.now() - timedelta(days=days_back)
        
        # Sync both stores
        for config in [GENEWAY_CONFIG, OPTIWAY_CONFIG]:
            try:
                print(f"Syncing {config['provider_name']} orders from {sync_from}")
                
                api = DualWooCommerceAPI(config)
                page = 1
                
                while True:
                    print(f"Fetching {config['provider_name']} page {page}...")
                    orders = api.get_orders(per_page=100, page=page, after=sync_from)
                    
                    if not orders:
                        break
                    
                    for wc_order in orders:
                        # Check if order already exists
                        existing_order = Order.query.filter_by(woocommerce_id=wc_order['id']).first()
                        
                        # Map WooCommerce order to local format
                        order_data = map_woocommerce_to_local_order(wc_order, config['provider_name'])
                        
                        if existing_order:
                            # Update existing order
                            for key, value in order_data.items():
                                setattr(existing_order, key, value)
                            updated_orders += 1
                            print(f"Updated {config['provider_name']} order #{wc_order['id']}")
                        else:
                            # Create new order
                            new_order = Order(**order_data)
                            db.session.add(new_order)
                            new_orders += 1
                            print(f"Added new {config['provider_name']} order #{wc_order['id']}")
                        
                        total_synced += 1
                    
                    # Check if there are more pages
                    if len(orders) < 100:
                        break
                    page += 1
                
            except Exception as e:
                print(f"Error syncing {config['provider_name']}: {e}")
                continue
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\nDual sync completed!")
            print(f"   Total processed: {total_synced}")
            print(f"   New orders: {new_orders}")
            print(f"   Updated orders: {updated_orders}")
            
            return {
                'success': True,
                'total_synced': total_synced,
                'new_orders': new_orders,
                'updated_orders': updated_orders
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"Error committing to database: {e}")
            return {
                'success': False,
                'error': str(e)
            }

if __name__ == "__main__":
    result = sync_both_woocommerce_stores(days_back=7)
    print(f"Sync result: {result}")


