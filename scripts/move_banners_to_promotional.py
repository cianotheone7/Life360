#!/usr/bin/env python3
"""
Script to move banners and gazebos from Stock Items to Promotional Items
Ensures all quantities, barcodes, and details are preserved
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set DATABASE_URL for production
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db, StockItem, StockUnit, PromotionalItem
from datetime import datetime

# Items to move - exact names from stock
ITEMS_TO_MOVE = [
    "Optiway Pull Up Banners",
    "Intelligene Pull Up Banners",
    "Geko Pull Up Banners",
    "Enbiosis SA Gazebo",
    "Enbiosis SA Pull Up Banners"
]

def move_banners_to_promotional():
    """Move banner and gazebo items from stock to promotional items"""
    with app.app_context():
        print("=" * 80)
        print("MOVING BANNERS AND GAZEBOS TO PROMOTIONAL ITEMS")
        print("=" * 80)
        
        moved_items = []
        
        for item_name in ITEMS_TO_MOVE:
            print(f"\nProcessing: {item_name}")
            print("-" * 80)
            
            # Find the stock item
            stock_item = StockItem.query.filter_by(name=item_name).first()
            
            if not stock_item:
                print(f"  ⚠️  WARNING: '{item_name}' not found in stock")
                continue
            
            # Get all units for this item
            units = StockUnit.query.filter_by(item_id=stock_item.id).all()
            total_units = len(units)
            in_stock_units = len([u for u in units if u.status == "In Stock"])
            assigned_units = len([u for u in units if u.status == "Assigned"])
            
            print(f"  Stock Item ID: {stock_item.id}")
            print(f"  Provider: {stock_item.provider}")
            print(f"  Total Units: {total_units}")
            print(f"  In Stock: {in_stock_units}")
            print(f"  Assigned: {assigned_units}")
            
            # Determine category
            if "Gazebo" in item_name:
                category = "Gazebo"
            elif "Banner" in item_name or "Pull Up" in item_name:
                category = "Banner"
            else:
                category = "Other"
            
            # Create promotional item
            promo_item = PromotionalItem(  # type: ignore[call-arg]
                name=item_name,
                category=category,
                description=f"Transferred from stock management. Original provider: {stock_item.provider}",
                quantity=total_units,
                available_quantity=in_stock_units,
                location=None,  # Can be updated later
                condition="Good",  # Default condition
                purchase_date=stock_item.received_date if hasattr(stock_item, 'received_date') else None,
                cost=None,  # Cost not tracked in stock items
                notes=f"Original stock item ID: {stock_item.id}. Provider: {stock_item.provider}. "
                      f"Total units: {total_units}, In stock: {in_stock_units}, Assigned: {assigned_units}. "
                      f"Barcodes preserved in stock_unit table.",
                created_at=datetime.utcnow(),
                signed_out=False
            )
            
            db.session.add(promo_item)
            db.session.flush()  # Get the ID
            
            print(f"  ✓ Created promotional item ID: {promo_item.id}")
            print(f"    Category: {category}")
            print(f"    Quantity: {total_units}")
            print(f"    Available: {in_stock_units}")
            
            # Keep barcodes in stock_unit table for reference
            # Update notes to reference the promotional item
            for unit in units:
                if not unit.promotional_notes:
                    unit.promotional_notes = f"Moved to Promotional Item ID {promo_item.id}: {item_name}"
                print(f"    Barcode {unit.barcode}: {unit.status}")
            
            # Mark the stock item as moved (don't delete it, preserve for history)
            stock_item.notes = (stock_item.notes or "") + f"\n[MOVED TO PROMOTIONAL ITEMS #{promo_item.id} on {datetime.utcnow().strftime('%Y-%m-%d')}]"
            
            moved_items.append({
                'name': item_name,
                'stock_id': stock_item.id,
                'promo_id': promo_item.id,
                'units': total_units
            })
            
            print(f"  ✓ Updated {len(units)} barcode records")
        
        # Commit all changes
        db.session.commit()
        
        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"\nTotal items moved: {len(moved_items)}")
        
        for item in moved_items:
            print(f"\n  ✓ {item['name']}")
            print(f"    Stock ID: {item['stock_id']} → Promotional ID: {item['promo_id']}")
            print(f"    Units/Barcodes: {item['units']}")
        
        print("\n" + "=" * 80)
        print("✓ MIGRATION COMPLETE")
        print("=" * 80)
        print("\nNOTES:")
        print("- All barcodes are preserved in the stock_unit table")
        print("- Original stock items are marked but not deleted (for history)")
        print("- Quantities and availability are accurately transferred")
        print("- You can now manage these items in the Gifts & Banners page")
        print("\n")

if __name__ == "__main__":
    try:
        move_banners_to_promotional()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
