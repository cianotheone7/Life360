"""
Add multiple stock items to Azure PostgreSQL database
- Magnesium Glycinate: MG000001 to MG000471 (471 units)
- Methylation Support: MS000002 to MS000505 (504 units)
- NAC: NAC000001 to NAC000474 (474 units)
All under Healthy Me provider
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from datetime import datetime, timedelta
from app import app, db, StockItem, StockUnit

def add_stock_items():
    """Add multiple stock items to Azure PostgreSQL."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Define stock items to add
            items_to_add = [
                {
                    "name": "Magnesium Glycinate",
                    "prefix": "MG",
                    "start": 1,
                    "count": 471,
                    "total": 471
                },
                {
                    "name": "Methylation Support",
                    "prefix": "MS",
                    "start": 2,  # Starts at MS000002
                    "count": 504,
                    "total": 504
                },
                {
                    "name": "NAC",
                    "prefix": "NAC",
                    "start": 1,
                    "count": 474,
                    "total": 474
                }
            ]
            
            for item_config in items_to_add:
                name = item_config["name"]
                prefix = item_config["prefix"]
                start_num = item_config["start"]
                count = item_config["count"]
                total_stock = item_config["total"]
                
                print(f"\n{'='*60}")
                print(f"Processing: {name}")
                print(f"{'='*60}")
                
                # Find existing stock item
                stock_item = StockItem.query.filter_by(
                    name=name,
                    provider="Healthy Me"
                ).first()
                
                if stock_item:
                    print(f"[DELETE] Found existing StockItem: {name} (ID: {stock_item.id})")
                    
                    # Delete all stock units for this item
                    deleted_units = StockUnit.query.filter(
                        StockUnit.barcode.like(f'{prefix}%'),
                        StockUnit.item_id == stock_item.id
                    ).delete(synchronize_session=False)
                    print(f"[DELETE] Deleted {deleted_units} existing stock units")
                    
                    # Delete the stock item
                    db.session.delete(stock_item)
                    db.session.commit()
                    print(f"[DELETE] Deleted StockItem: {name}")
                
                # Create new stock item
                stock_item = StockItem(
                    name=name,
                    provider="Healthy Me",
                    code_type="Supplement",
                    current_stock=total_stock,
                    received_date=datetime.now().date(),
                    expiry_date=(datetime.now() + timedelta(days=730)).date()  # 2 years from now
                )
                db.session.add(stock_item)
                db.session.flush()  # Get the ID
                print(f"[OK] Created StockItem: {name} (ID: {stock_item.id})")
                
                # Add stock units
                added_count = 0
                skipped_count = 0
                end_num = start_num + count - 1
                
                for i in range(start_num, start_num + count):
                    if prefix == "NAC":
                        barcode = f"{prefix}{i:06d}"  # NAC000001 format
                    else:
                        barcode = f"{prefix}{i:06d}"  # MG000001, MS000002 format
                    
                    # Check if barcode already exists
                    existing_unit = StockUnit.query.filter_by(barcode=barcode).first()
                    if existing_unit:
                        if skipped_count < 5:  # Only show first 5 skips
                            print(f"[SKIP] {barcode} - already exists")
                        skipped_count += 1
                        continue
                    
                    # Create new stock unit
                    unit = StockUnit(
                        barcode=barcode,
                        batch_number=f"BATCH-{prefix}-2025-001",
                        status="In Stock",
                        item_id=stock_item.id,
                        last_update=datetime.now()
                    )
                    db.session.add(unit)
                    added_count += 1
                    
                    # Commit in batches of 100 to avoid timeout
                    if added_count % 100 == 0:
                        db.session.commit()
                        print(f"[OK] Added {added_count} units so far...")
                
                # Final commit for this item
                db.session.commit()
                
                print(f"\n[SUCCESS] {name} Stock Addition Complete!")
                print(f"  Added: {added_count} new units")
                print(f"  Skipped: {skipped_count} existing units")
                print(f"  Barcode Range: {prefix}{start_num:06d} to {prefix}{end_num:06d}")
                print(f"  Total Stock Count: {stock_item.current_stock}")
            
            print("\n" + "="*60)
            print("[SUCCESS] All Stock Items Added Successfully!")
            print("="*60)
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/stock")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_stock_items()




