"""
Delete stock items W3 and T3 from Azure PostgreSQL database
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db, StockItem, StockUnit

def delete_stock_items():
    """Delete W3 and T3 stock items and their units."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Items to delete
            items_to_delete = ["W3", "T3"]
            
            for item_name in items_to_delete:
                print(f"\n{'='*60}")
                print(f"Processing: {item_name}")
                print(f"{'='*60}")
                
                # Find stock item
                stock_item = StockItem.query.filter_by(name=item_name).first()
                
                if not stock_item:
                    print(f"[SKIP] StockItem '{item_name}' not found")
                    continue
                
                print(f"[OK] Found StockItem: {item_name} (ID: {stock_item.id})")
                print(f"[OK] Current Stock: {stock_item.current_stock}")
                
                # Delete all stock units for this item
                deleted_units = StockUnit.query.filter_by(item_id=stock_item.id).delete(synchronize_session=False)
                print(f"[DELETE] Deleted {deleted_units} stock units")
                
                # Delete the stock item
                db.session.delete(stock_item)
                db.session.commit()
                print(f"[DELETE] Deleted StockItem: {item_name}")
                print(f"[OK] '{item_name}' completely removed from database")
            
            print("\n" + "="*60)
            print("[SUCCESS] Stock Items Deleted Successfully!")
            print("="*60)
            print("Deleted items:")
            print("  - W3 (ID: 32) - 112 units")
            print("  - T3 (ID: 31) - 426 units")
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/stock")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    delete_stock_items()




