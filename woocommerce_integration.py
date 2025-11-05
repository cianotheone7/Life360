#!/usr/bin/env python3
"""
WooCommerce Integration for Life360 Dashboard
Pulls orders from WooCommerce and syncs them with the local database
"""
import requests
from requests.auth import HTTPBasicAuth
import json
from datetime import datetime, timedelta
from app import app, db, Order
import logging

# WooCommerce API Configuration
WOOCOMMERCE_CONFIG = {
    'base_url': 'https://geneway.co.za',  # Your WooCommerce site URL
    'consumer_key': 'ck_ce467c6d4f0b3d980124440c6b28fb26faa06817',
    'consumer_secret': 'cs_05d08a784db62bd25f2346c8e02dd01ae8ba33de',
    'api_version': 'wc/v3'
}

class WooCommerceAPI:
    """WooCommerce REST API client"""
    
    def __init__(self):
        self.base_url = f"{WOOCOMMERCE_CONFIG['base_url']}/wp-json/{WOOCOMMERCE_CONFIG['api_version']}"
        self.auth = HTTPBasicAuth(
            WOOCOMMERCE_CONFIG['consumer_key'], 
            WOOCOMMERCE_CONFIG['consumer_secret']
        )
        self.session = requests.Session()
        self.session.auth = self.auth
    
    def get_orders(self, status='any', per_page=100, page=1, after=None):
        """
        Fetch orders from WooCommerce
        
        Args:
            status: Order status (any, pending, processing, on-hold, completed, cancelled, refunded, failed)
            per_page: Number of orders per page (max 100)
            page: Page number
            after: ISO8601 date to get orders after this date
        """
        url = f"{self.base_url}/orders"
        params = {
            'status': status,
            'per_page': per_page,
            'page': page,
            'orderby': 'date',
            'order': 'desc'
        }
        
        if after:
            params['after'] = after
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"WooCommerce API error: {e}")
            return []
    
    def get_order(self, order_id):
        """Get a specific order by ID"""
        url = f"{self.base_url}/orders/{order_id}"
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"WooCommerce API error getting order {order_id}: {e}")
            return None

def map_woocommerce_to_local_order(wc_order):
    """
    Map WooCommerce order data to local Order model format
    """
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
        'provider': 'Geneway' if 'geneway.co.za' in WOOCOMMERCE_CONFIG['base_url'] else 'Optiway',  # Dynamic provider based on API URL
        'ordered_at': datetime.fromisoformat(wc_order.get('date_created', '').replace('Z', '+00:00')),
        'name': billing.get('first_name', ''),
        'surname': billing.get('last_name', ''),
        'raw_api_data': raw_api_data  # Store complete API response
    }

def sync_woocommerce_orders(days_back=7):
    """
    Sync WooCommerce orders to local database
    
    Args:
        days_back: Number of days back to sync orders (default: 7)
    """
    with app.app_context():
        wc_api = WooCommerceAPI()
        
        # Calculate date to sync from
        sync_from = datetime.now() - timedelta(days=days_back)
        sync_from_iso = sync_from.isoformat()
        
        print(f"Syncing WooCommerce orders from {sync_from.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Get orders from WooCommerce
            page = 1
            total_synced = 0
            total_updated = 0
            total_new = 0
            
            while True:
                print(f"Fetching page {page}...")
                wc_orders = wc_api.get_orders(
                    status='any',
                    per_page=100,
                    page=page,
                    after=sync_from_iso
                )
                
                if not wc_orders:
                    break
                
                for wc_order in wc_orders:
                    try:
                        # Map WooCommerce order to local format
                        order_data = map_woocommerce_to_local_order(wc_order)
                        
                        # Check if order already exists (by WooCommerce ID)
                        existing_order = Order.query.filter_by(
                            woocommerce_id=order_data['woocommerce_id']
                        ).first()
                        
                        if existing_order:
                            # Update existing order
                            for key, value in order_data.items():
                                if key != 'woocommerce_id':  # Don't update the ID
                                    setattr(existing_order, key, value)
                            total_updated += 1
                            print(f"Updated order #{order_data['woocommerce_id']}")
                        else:
                            # Create new order
                            new_order = Order(**order_data)
                            db.session.add(new_order)
                            total_new += 1
                            print(f"Added new order #{order_data['woocommerce_id']}")
                        
                        total_synced += 1
                        
                    except Exception as e:
                        print(f"Error processing order #{wc_order.get('id', 'unknown')}: {e}")
                        continue
                
                # If we got less than 100 orders, we're done
                if len(wc_orders) < 100:
                    break
                
                page += 1
            
            # Commit all changes
            db.session.commit()
            
            print(f"\nSync completed!")
            print(f"   Total processed: {total_synced}")
            print(f"   New orders: {total_new}")
            print(f"   Updated orders: {total_updated}")
            
            return {
                'success': True,
                'total_synced': total_synced,
                'new_orders': total_new,
                'updated_orders': total_updated
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"Sync failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

def test_woocommerce_connection():
    """Test WooCommerce API connection"""
    print("Testing WooCommerce API connection...")
    
    wc_api = WooCommerceAPI()
    
    try:
        # Try to get just 1 order to test connection
        orders = wc_api.get_orders(per_page=1)
        
        if orders:
            print("Connection successful!")
            print(f"   Found {len(orders)} order(s)")
            if orders:
                order = orders[0]
                print(f"   Latest order: #{order.get('id')} - {order.get('status')} - ${order.get('total')}")
            return True
        else:
            print("No orders found or connection failed")
            return False
            
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("WooCommerce Integration for Life360 Dashboard")
    print("=" * 50)
    
    # Test connection first
    if test_woocommerce_connection():
        print("\n" + "=" * 50)
        
        # Ask user what to do
        print("Options:")
        print("1. Sync last 7 days of orders")
        print("2. Sync last 30 days of orders") 
        print("3. Sync all orders (be careful - might be a lot!)")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            sync_woocommerce_orders(days_back=7)
        elif choice == "2":
            sync_woocommerce_orders(days_back=30)
        elif choice == "3":
            # For all orders, we'll sync last 365 days
            sync_woocommerce_orders(days_back=365)
        else:
            print("Invalid choice")
    else:
        print("\nCannot proceed - fix connection issues first")
