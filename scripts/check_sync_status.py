#!/usr/bin/env python3
"""
Quick script to check if the WooCommerce sync service is working
"""
from app import app, Order, db
from datetime import datetime, timedelta

def check_sync_status():
    """Check the status of WooCommerce sync"""
    with app.app_context():
        # Get WooCommerce orders
        wc_orders = Order.query.filter(Order.woocommerce_id.isnot(None)).all()
        
        print("WooCommerce Sync Status")
        print("=" * 30)
        print(f"Total WooCommerce orders in database: {len(wc_orders)}")
        
        if wc_orders:
            # Show recent orders
            recent_orders = [o for o in wc_orders if o.ordered_at and o.ordered_at > datetime.now() - timedelta(days=1)]
            print(f"Orders from last 24 hours: {len(recent_orders)}")
            
            print("\nRecent WooCommerce orders:")
            for order in sorted(wc_orders, key=lambda x: x.ordered_at or datetime.min, reverse=True)[:5]:
                print(f"  - Order #{order.woocommerce_id}: {order.customer_name} - R{order.total_amount:.2f} - {order.status}")
        
        print(f"\nLast check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    check_sync_status()

