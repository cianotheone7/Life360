#!/usr/bin/env python3
"""
Clean up migration notes from promotional items
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db, PromotionalItem

def clean_notes():
    with app.app_context():
        print("=" * 80)
        print("CLEANING PROMOTIONAL ITEM NOTES")
        print("=" * 80)
        
        items = PromotionalItem.query.all()
        cleaned_count = 0
        
        for item in items:
            if item.notes and ("Transferred from stock management" in item.notes or "Original provider:" in item.notes):
                print(f"\n✓ Cleaning: {item.name}")
                print(f"  Old notes: {item.notes[:100]}...")
                item.notes = None
                cleaned_count += 1
            
            # Also clean description if it has the migration text
            if item.description and ("Transferred from stock management" in item.description or "Original provider:" in item.description):
                print(f"\n✓ Cleaning description: {item.name}")
                print(f"  Old description: {item.description[:100]}...")
                item.description = None
        
        db.session.commit()
        
        print("\n" + "=" * 80)
        print(f"✓ CLEANED {cleaned_count} ITEMS")
        print("=" * 80)

if __name__ == "__main__":
    clean_notes()
