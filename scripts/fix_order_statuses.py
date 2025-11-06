"""
Fix orders that have incorrect status values
Set status='Opted In' to status='Pending'
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from sqlalchemy import text
from app import app, db, Order

def fix_order_statuses():
    """Fix orders with incorrect status values."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Find orders with status='Opted In' (should be 'Pending')
            orders_to_fix = Order.query.filter_by(status="Opted In").all()
            
            print(f"\n{'='*60}")
            print("Fixing Order Statuses")
            print(f"{'='*60}")
            print(f"[INFO] Found {len(orders_to_fix)} orders with status='Opted In'")
            
            if len(orders_to_fix) == 0:
                print("[SKIP] No orders need fixing")
                return
            
            # Update all orders with status='Opted In' to status='Pending'
            fixed_count = 0
            for order in orders_to_fix:
                order.status = "Pending"
                fixed_count += 1
            
            db.session.commit()
            
            print(f"[OK] Fixed {fixed_count} orders - changed status from 'Opted In' to 'Pending'")
            
            print("\n" + "="*60)
            print("[SUCCESS] Order Statuses Fixed!")
            print("="*60)
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    fix_order_statuses()




