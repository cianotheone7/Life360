"""
Add Enbiosis and Intelligene kit stock items to Azure PostgreSQL database
- Enbiosis Direct Patient Kits
- Enbiosis Umvuzo Kits
- Intelligene Direct Patient Kits
- Intelligene Umvuzo Kits
- Intelligene Fedhealth Kits
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from datetime import datetime, timedelta
from app import app, db, StockItem

def add_kit_stock_items():
    """Add Enbiosis and Intelligene kit stock items to Azure PostgreSQL."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Define stock items to add
            items_to_add = [
                {
                    "name": "Direct Patient Kits",
                    "provider": "Enbiosis",
                    "code_type": "Kit"
                },
                {
                    "name": "Umvuzo Kits",
                    "provider": "Enbiosis",
                    "code_type": "Kit"
                },
                {
                    "name": "Direct Patient Kits",
                    "provider": "Intelligene",
                    "code_type": "Kit"
                },
                {
                    "name": "Umvuzo Kits",
                    "provider": "Intelligene",
                    "code_type": "Kit"
                },
                {
                    "name": "Fedhealth Kits",
                    "provider": "Intelligene",
                    "code_type": "Kit"
                }
            ]
            
            print(f"\n{'='*60}")
            print(f"Adding {len(items_to_add)} Stock Items")
            print(f"{'='*60}\n")
            
            added_count = 0
            skipped_count = 0
            
            for item_config in items_to_add:
                name = item_config["name"]
                provider = item_config["provider"]
                code_type = item_config["code_type"]
                
                # Check if stock item already exists
                existing_item = StockItem.query.filter_by(
                    name=name,
                    provider=provider
                ).first()
                
                if existing_item:
                    print(f"[SKIP] {provider} - {name} already exists (ID: {existing_item.id}, Stock: {existing_item.current_stock})")
                    skipped_count += 1
                    continue
                
                # Create new stock item
                stock_item = StockItem(
                    name=name,
                    provider=provider,
                    code_type=code_type,
                    current_stock=0,  # Start with 0 stock, can be updated later
                    received_date=datetime.now().date(),
                    expiry_date=None  # No expiry date set initially
                )
                db.session.add(stock_item)
                db.session.flush()  # Get the ID
                
                print(f"[OK] Created: {provider} - {name} (ID: {stock_item.id})")
                added_count += 1
            
            # Commit all changes
            db.session.commit()
            
            print(f"\n{'='*60}")
            print("[SUCCESS] Stock Items Addition Complete!")
            print(f"{'='*60}")
            print(f"  Added: {added_count} new stock items")
            print(f"  Skipped: {skipped_count} existing items")
            print(f"\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/stock")
            print("\nNote: Stock items are created with 0 current stock.")
            print("You can add stock units later through the web interface or another script.")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_kit_stock_items()


