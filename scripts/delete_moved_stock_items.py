#!/usr/bin/env python3
"""
Script to delete the moved banner and gazebo items from stock
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db, StockItem, StockUnit

ITEMS_TO_DELETE = [
    "Optiway Pull Up Banners",
    "Intelligene Pull Up Banners",
    "Geko Pull Up Banners",
    "Enbiosis SA Gazebo",
    "Enbiosis SA Pull Up Banners"
]

def delete_stock_items():
    with app.app_context():
        print("=" * 80)
        print("REMOVING MOVED ITEMS FROM STOCK PAGE")
        print("=" * 80)
        
        for item_name in ITEMS_TO_DELETE:
            stock_item = StockItem.query.filter_by(name=item_name).first()
            
            if not stock_item:
                print(f"  ⚠️  '{item_name}' not found in stock")
                continue
            
            print(f"\n✓ Deleting: {item_name} (ID: {stock_item.id})")
            
            # Delete all units first
            units = StockUnit.query.filter_by(item_id=stock_item.id).all()
            print(f"  - Deleting {len(units)} stock units")
            for unit in units:
                db.session.delete(unit)
            
            # Delete the stock item
            db.session.delete(stock_item)
        
        db.session.commit()
        print("\n" + "=" * 80)
        print("✓ DELETION COMPLETE - Items removed from Stock page")
        print("=" * 80)

if __name__ == "__main__":
    delete_stock_items()
