#!/usr/bin/env python3
"""
Add fillout_submission_id column to order table
"""
from app import app, db
from sqlalchemy import text

def add_fillout_column():
    with app.app_context():
        try:
            # Add the column
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "order" ADD COLUMN fillout_submission_id VARCHAR(100);'))
                conn.commit()
                print("Added fillout_submission_id column")
                
                # Add unique index
                conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS idx_order_fillout_submission_id ON "order"(fillout_submission_id);'))
                conn.commit()
                print("Added unique index for fillout_submission_id")
            
        except Exception as e:
            if "already exists" in str(e) or "duplicate column name" in str(e):
                print("Column already exists")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    add_fillout_column()
