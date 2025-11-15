#!/usr/bin/env python3
"""
Create promotional_transaction table for tracking sign-outs and returns
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from app import app, db

def create_transaction_table():
    with app.app_context():
        print("=" * 80)
        print("CREATING PROMOTIONAL_TRANSACTION TABLE")
        print("=" * 80)
        
        # Create all tables (will only create missing ones)
        db.create_all()
        
        print("\n✓ promotional_transaction table created successfully")
        print("\nThis table will track:")
        print("  - All sign-outs with barcode, person, purpose, and expected return date")
        print("  - All returns with person and condition notes")
        print("  - Complete history of all transactions")
        print("\n" + "=" * 80)

if __name__ == "__main__":
    create_transaction_table()
