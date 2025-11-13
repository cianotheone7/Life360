#!/usr/bin/env python
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Set the Azure database URL
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require'

# Import after setting env
from app import app, db, StockItem, StockUnit

with app.app_context():
    print("=== Recent Stock Items ===")
    try:
        items = StockItem.query.order_by(StockItem.id.desc()).limit(10).all()
        for item in items:
            units = StockUnit.query.filter_by(item_id=item.id).all()
            print(f"ID: {item.id}, Name: '{item.name}', Stock: {item.current_stock}, Provider: {item.provider}, Units: {len(units)}")
            if units:
                for unit in units[:3]:
                    print(f"  - Barcode: {unit.barcode}, Status: {unit.status}")
                if len(units) > 3:
                    print(f"  ... and {len(units) - 3} more units")
        
        print(f"\n=== Total items: {StockItem.query.count()} ===")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
