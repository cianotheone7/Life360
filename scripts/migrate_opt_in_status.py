"""
Add opt_in_status column to existing orders
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from sqlalchemy import text
from app import app, db

def add_opt_in_status_column():
    """Add opt_in_status column to Order table if it doesn't exist."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            # Check if column exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='order' AND column_name='opt_in_status'
            """)
            
            result = db.session.execute(check_query).fetchone()
            
            if result:
                print("[SKIP] Column 'opt_in_status' already exists")
            else:
                # Add the column
                alter_query = text("""
                    ALTER TABLE "order" 
                    ADD COLUMN opt_in_status VARCHAR(20) DEFAULT 'Opted In'
                """)
                db.session.execute(alter_query)
                db.session.commit()
                print("[OK] Added 'opt_in_status' column to Order table")
            
            # Set all existing orders to NULL (Pending) instead of defaulting to "Opted In"
            update_query = text("""
                UPDATE "order" 
                SET opt_in_status = NULL 
                WHERE opt_in_status = 'Opted In'
            """)
            result = db.session.execute(update_query)
            db.session.commit()
            
            updated_count = result.rowcount
            print(f"[OK] Set {updated_count} existing orders to NULL (Pending) opt-in status")
            
            print("\n" + "="*60)
            print("[SUCCESS] Migration Complete!")
            print("="*60)
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_opt_in_status_column()

