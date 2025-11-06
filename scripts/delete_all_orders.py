"""
Delete all orders, order items, and order units from Azure PostgreSQL database
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db, Order, OrderItem, OrderUnit

def delete_all_orders():
    """Delete all orders and order items."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Count orders before deletion
            total_orders = Order.query.count()
            total_order_items = OrderItem.query.count()
            total_order_units = OrderUnit.query.count()
            
            print(f"\n{'='*60}")
            print("Deleting All Orders")
            print(f"{'='*60}")
            print(f"[INFO] Found {total_orders} orders")
            print(f"[INFO] Found {total_order_items} order items")
            print(f"[INFO] Found {total_order_units} order units")
            
            if total_orders == 0 and total_order_items == 0 and total_order_units == 0:
                print("[SKIP] No orders, order items, or order units found to delete")
                return
            
            # Delete all order units first (foreign key constraint)
            deleted_units = OrderUnit.query.delete()
            print(f"[DELETE] Deleted {deleted_units} order units")
            
            # Delete all order items (foreign key constraint)
            deleted_items = OrderItem.query.delete()
            print(f"[DELETE] Deleted {deleted_items} order items")
            
            # Delete all orders
            deleted_orders = Order.query.delete()
            print(f"[DELETE] Deleted {deleted_orders} orders")
            
            # Commit changes
            db.session.commit()
            
            print("\n" + "="*60)
            print("[SUCCESS] All Orders Deleted Successfully!")
            print("="*60)
            print(f"  - Deleted {deleted_orders} orders")
            print(f"  - Deleted {deleted_items} order items")
            print(f"  - Deleted {deleted_units} order units")
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    delete_all_orders()

