"""
Add L-Theanine stock items to Azure PostgreSQL database
Barcodes: TH000001 to TH000495 (495 units)
Provider: Healthy Me
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from datetime import datetime, timedelta
from app import app, db, StockItem, StockUnit

def add_theanine_stock():
    """Delete existing L-Theanine stock and add 495 units to Azure PostgreSQL."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Find existing L-Theanine stock item for Healthy Me
            stock_item = StockItem.query.filter_by(
                name="L-Theanine",
                provider="Healthy Me"
            ).first()
            
            if stock_item:
                print(f"[DELETE] Found existing StockItem: L-Theanine (ID: {stock_item.id})")
                
                # Delete all stock units for this item (TH000001 to TH001000 range)
                deleted_units = StockUnit.query.filter(
                    StockUnit.barcode.like('TH%'),
                    StockUnit.item_id == stock_item.id
                ).delete(synchronize_session=False)
                print(f"[DELETE] Deleted {deleted_units} existing stock units")
                
                # Delete the stock item
                db.session.delete(stock_item)
                db.session.commit()
                print(f"[DELETE] Deleted StockItem: L-Theanine")
            
            # Create new stock item
            stock_item = StockItem(
                name="L-Theanine",
                provider="Healthy Me",
                code_type="Supplement",
                current_stock=495,
                received_date=datetime.now().date(),
                expiry_date=(datetime.now() + timedelta(days=730)).date()  # 2 years from now
            )
            db.session.add(stock_item)
            db.session.flush()  # Get the ID
            print(f"[OK] Created StockItem: L-Theanine (ID: {stock_item.id})")
            
            # Add 495 stock units with barcodes TH000001 to TH000495
            added_count = 0
            skipped_count = 0
            
            for i in range(1, 496):
                barcode = f"TH{i:06d}"  # Format: TH000001, TH000002, etc.
                
                # Check if barcode already exists
                existing_unit = StockUnit.query.filter_by(barcode=barcode).first()
                if existing_unit:
                    if skipped_count < 10:  # Only show first 10 skips
                        print(f"[SKIP] {barcode} - already exists")
                    skipped_count += 1
                    continue
                
                # Create new stock unit
                unit = StockUnit(
                    barcode=barcode,
                    batch_number=f"BATCH-LT-2025-001",
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
            
            # Final commit
            db.session.commit()
            
            print("\n" + "="*60)
            print("[SUCCESS] L-Theanine Stock Addition Complete!")
            print("="*60)
            print(f"Stock Item: L-Theanine (Healthy Me)")
            print(f"Added: {added_count} new units")
            print(f"Skipped: {skipped_count} existing units")
            print(f"Barcode Range: TH000001 to TH000495")
            print(f"Batch Number: BATCH-LT-2025-001")
            print(f"Total Stock Count: {stock_item.current_stock}")
            print("="*60)
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/stock")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_theanine_stock()

