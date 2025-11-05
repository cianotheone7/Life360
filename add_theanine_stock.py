"""
Add L-Theanine stock items to database
Barcodes: TH000001 to TH000210 (210 units)
Provider: Healthy Me
"""
import os
from datetime import datetime, timedelta
from app import app, db, StockItem, StockUnit

def add_theanine_stock():
    """Add L-Theanine stock with 1000 units."""
    with app.app_context():
        try:
            # Check if L-Theanine stock item already exists for Healthy Me
            stock_item = StockItem.query.filter_by(
                name="L-Theanine",
                provider="Healthy Me"
            ).first()
            
            if not stock_item:
                # Create new stock item
                stock_item = StockItem(
                    name="L-Theanine",
                    provider="Healthy Me",
                    code_type="Supplement",
                    current_stock=210,
                    received_date=datetime.now().date(),
                    expiry_date=(datetime.now() + timedelta(days=730)).date()  # 2 years from now
                )
                db.session.add(stock_item)
                db.session.flush()  # Get the ID
                print(f"[OK] Created StockItem: L-Theanine (ID: {stock_item.id})")
            else:
                print(f"[OK] Found existing StockItem: L-Theanine (ID: {stock_item.id})")
                # Update stock count
                stock_item.current_stock = stock_item.current_stock + 210
            
            # Add 210 stock units with barcodes TH000001 to TH000210
            added_count = 0
            skipped_count = 0
            
            for i in range(1, 211):
                barcode = f"TH{i:06d}"  # Format: TH000001, TH000002, etc.
                
                # Check if barcode already exists
                existing_unit = StockUnit.query.filter_by(barcode=barcode).first()
                if existing_unit:
                    print(f"[SKIP] {barcode} - already exists")
                    skipped_count += 1
                    continue
                
                # Create new stock unit
                unit = StockUnit(
                    barcode=barcode,
                    batch_number=f"BATCH-LT-2025-001",
                    status="In Stock",
                    item_id=stock_item.id,
                    last_update=datetime.utcnow()
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
            print(f"Barcode Range: TH000001 to TH000210")
            print(f"Batch Number: BATCH-LT-2025-001")
            print(f"Total Stock Count: {stock_item.current_stock}")
            print("="*60)
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_theanine_stock()

