#!/usr/bin/env python3
"""
Add raw_api_data column to order table
"""
from app import app, db
from sqlalchemy import text

def add_raw_data_column():
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "order" ADD COLUMN raw_api_data TEXT;'))
                conn.commit()
                print("Added raw_api_data column")
            
        except Exception as e:
            if "already exists" in str(e) or "duplicate column name" in str(e):
                print("Column already exists")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    add_raw_data_column()


