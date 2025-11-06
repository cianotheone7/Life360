"""
Update batch numbers and expiry dates for stock items in Azure PostgreSQL database
- NAC (Glutathione): BN 25J091, EXP 09/2027
- Magnesium Glycinate: BN 251246, EXP 08/2027
- Methylated Support (DNA Renew): BN 25J092, EXP 09/2027
- L-Theanine (Mind Balance): BN 25J093, EXP 09/2027
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from datetime import datetime
from app import app, db, StockItem, StockUnit

def update_batch_numbers():
    """Update batch numbers and expiry dates for stock items."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Define updates for each item
            updates = [
                {
                    "name": "NAC",
                    "batch_number": "25J091",
                    "expiry_month": 9,  # September
                    "expiry_year": 2027
                },
                {
                    "name": "Magnesium Glycinate",
                    "batch_number": "251246",
                    "expiry_month": 8,  # August
                    "expiry_year": 2027
                },
                {
                    "name": "Methylation Support",
                    "batch_number": "25J092",
                    "expiry_month": 9,  # September
                    "expiry_year": 2027
                },
                {
                    "name": "L-Theanine",
                    "batch_number": "25J093",
                    "expiry_month": 9,  # September
                    "expiry_year": 2027
                }
            ]
            
            for update_config in updates:
                name = update_config["name"]
                batch_number = update_config["batch_number"]
                expiry_month = update_config["expiry_month"]
                expiry_year = update_config["expiry_year"]
                
                print(f"\n{'='*60}")
                print(f"Updating: {name}")
                print(f"{'='*60}")
                
                # Find stock item
                stock_item = StockItem.query.filter_by(
                    name=name,
                    provider="Healthy Me"
                ).first()
                
                if not stock_item:
                    print(f"[SKIP] StockItem '{name}' not found")
                    continue
                
                print(f"[OK] Found StockItem: {name} (ID: {stock_item.id})")
                
                # Update expiry date
                expiry_date = datetime(expiry_year, expiry_month, 1).date()
                stock_item.expiry_date = expiry_date
                print(f"[OK] Updated expiry date to: {expiry_date.strftime('%m/%Y')}")
                
                # Update all stock units with new batch number
                units = StockUnit.query.filter_by(item_id=stock_item.id).all()
                updated_count = 0
                
                for unit in units:
                    unit.batch_number = batch_number
                    updated_count += 1
                
                db.session.commit()
                
                print(f"[OK] Updated {updated_count} stock units with batch number: {batch_number}")
                print(f"[OK] Stock item '{name}' updated successfully!")
            
            print("\n" + "="*60)
            print("[SUCCESS] All Batch Numbers and Expiry Dates Updated!")
            print("="*60)
            print("\nSummary:")
            print("  - NAC (Glutathione): BN 25J091, EXP 09/2027")
            print("  - Magnesium Glycinate: BN 251246, EXP 08/2027")
            print("  - Methylated Support (DNA Renew): BN 25J092, EXP 09/2027")
            print("  - L-Theanine (Mind Balance): BN 25J093, EXP 09/2027")
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/stock")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    update_batch_numbers()




