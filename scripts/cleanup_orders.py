#!/usr/bin/env python3
"""
Clean up test orders and check current orders
"""
from app import app, Order, db

def cleanup_orders():
    with app.app_context():
        # Check order #1363
        order_1363 = Order.query.filter(Order.woocommerce_id == 1363).first()
        if order_1363:
            print(f"Order #1363: {order_1363.customer_name} - R{order_1363.total_amount} - {order_1363.provider}")
            if order_1363.customer_name and 'test' in order_1363.customer_name.lower():
                print("Deleting test order #1363")
                db.session.delete(order_1363)
                db.session.commit()
        
        # Show current orders
        all_orders = Order.query.all()
        print(f"\nCurrent orders in database: {len(all_orders)}")
        
        for order in all_orders:
            wc_id = f"WC#{order.woocommerce_id}" if order.woocommerce_id else ""
            fillout_id = f"Fillout#{order.fillout_submission_id[:8]}..." if order.fillout_submission_id else ""
            order_id = wc_id or fillout_id or "Regular"
            
            customer_display = order.customer_name or f"{order.name or ''} {order.surname or ''}".strip() or 'Unknown'
            print(f"  - {customer_display} ({order.provider}) {order_id}")

if __name__ == "__main__":
    cleanup_orders()
