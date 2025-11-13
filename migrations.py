"""
Database migration system for Life360 application.
"""
import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
import logging

logger = logging.getLogger(__name__)


class Migration:
    """Represents a database migration."""
    
    def __init__(self, version: str, description: str, up_sql: str, down_sql: str = ""):
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.applied_at: Optional[datetime] = None
    
    def __repr__(self):
        return f"Migration({self.version}, {self.description})"


class MigrationManager:
    """Manages database migrations."""
    
    def __init__(self, db: SQLAlchemy):
        self.db = db
        self.migrations: List[Migration] = []
        self._init_migrations_table()
        self._load_migrations()
    
    def _init_migrations_table(self):
        """Initialize the migrations tracking table."""
        try:
            with self.db.engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS migrations (
                        version VARCHAR(50) PRIMARY KEY,
                        description TEXT NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize migrations table: {e}")
            raise
    
    def _load_migrations(self):
        """Load all available migrations."""
        # Define migrations
        migrations = [
            Migration(
                version="001",
                description="Create initial tables",
                up_sql="""
                    CREATE TABLE IF NOT EXISTS stock_item (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(120) NOT NULL,
                        expiry_date DATE,
                        received_date DATE,
                        code_type VARCHAR(20) NOT NULL DEFAULT 'Kit',
                        person_requested VARCHAR(120),
                        request_datetime DATETIME,
                        current_stock INTEGER NOT NULL DEFAULT 0,
                        provider VARCHAR(120)
                    );
                    
                    CREATE TABLE IF NOT EXISTS stock_unit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        barcode VARCHAR(120) UNIQUE NOT NULL,
                        batch_number VARCHAR(120),
                        status VARCHAR(40) NOT NULL DEFAULT 'In Stock',
                        item_id INTEGER NOT NULL,
                        last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (item_id) REFERENCES stock_item (id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS order_unit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        unit_id INTEGER NOT NULL,
                        assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (unit_id) REFERENCES stock_unit (id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS "order" (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR(120),
                        name VARCHAR(120),
                        surname VARCHAR(120),
                        practitioner_name VARCHAR(120),
                        ordered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(40) NOT NULL DEFAULT 'Pending',
                        notes TEXT,
                        email_status VARCHAR(60),
                        sent_out BOOLEAN DEFAULT 0,
                        received_back BOOLEAN DEFAULT 0,
                        kit_registered BOOLEAN DEFAULT 0,
                        results_sent BOOLEAN DEFAULT 0,
                        paid BOOLEAN DEFAULT 0,
                        invoiced BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME
                    );
                    
                    CREATE TABLE IF NOT EXISTS order_item (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        sku VARCHAR(120) NOT NULL,
                        qty INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY (order_id) REFERENCES "order" (id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS task (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(200) NOT NULL,
                        provider VARCHAR(120),
                        assignee VARCHAR(120),
                        due_date DATE,
                        status VARCHAR(40) NOT NULL DEFAULT 'Open',
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS document (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR(120) NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        stored_name VARCHAR(255) NOT NULL,
                        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS order_call_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        when DATETIME DEFAULT CURRENT_TIMESTAMP,
                        author VARCHAR(120),
                        summary TEXT NOT NULL,
                        outcome VARCHAR(60)
                    );
                    
                    CREATE TABLE IF NOT EXISTS practitioner (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR(80),
                        title VARCHAR(20),
                        first_name VARCHAR(120),
                        last_name VARCHAR(120),
                        email VARCHAR(200),
                        phone VARCHAR(40),
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS practitioner_flag (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pid INTEGER UNIQUE NOT NULL,
                        training BOOLEAN DEFAULT 0,
                        website BOOLEAN DEFAULT 0,
                        whatsapp BOOLEAN DEFAULT 0,
                        engagebay BOOLEAN DEFAULT 0,
                        onboarded BOOLEAN DEFAULT 0,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS sales_order_pdf (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename VARCHAR(255) NOT NULL,
                        file_data BLOB NOT NULL,
                        file_size INTEGER NOT NULL,
                        uploaded_by VARCHAR(120) NOT NULL,
                        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        content_type VARCHAR(100) DEFAULT 'application/pdf'
                    );
                """,
                down_sql="""
                    DROP TABLE IF EXISTS sales_order_pdf;
                    DROP TABLE IF EXISTS practitioner_flag;
                    DROP TABLE IF EXISTS practitioner;
                    DROP TABLE IF EXISTS order_call_log;
                    DROP TABLE IF EXISTS document;
                    DROP TABLE IF EXISTS task;
                    DROP TABLE IF EXISTS order_item;
                    DROP TABLE IF EXISTS "order";
                    DROP TABLE IF EXISTS order_unit;
                    DROP TABLE IF EXISTS stock_unit;
                    DROP TABLE IF EXISTS stock_item;
                """
            ),
            Migration(
                version="002",
                description="Add indexes for performance",
                up_sql="""
                    CREATE INDEX IF NOT EXISTS idx_stock_item_provider ON stock_item(provider);
                    CREATE INDEX IF NOT EXISTS idx_stock_item_name ON stock_item(name);
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_item_id ON stock_unit(item_id);
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_status ON stock_unit(status);
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_barcode ON stock_unit(barcode);
                    CREATE INDEX IF NOT EXISTS idx_order_provider ON "order"(provider);
                    CREATE INDEX IF NOT EXISTS idx_order_status ON "order"(status);
                    CREATE INDEX IF NOT EXISTS idx_order_created_at ON "order"(created_at);
                    CREATE INDEX IF NOT EXISTS idx_order_item_order_id ON order_item(order_id);
                    CREATE INDEX IF NOT EXISTS idx_practitioner_provider ON practitioner(provider);
                    CREATE INDEX IF NOT EXISTS idx_practitioner_email ON practitioner(email);
                    CREATE INDEX IF NOT EXISTS idx_task_status ON task(status);
                    CREATE INDEX IF NOT EXISTS idx_task_due_date ON task(due_date);
                    CREATE INDEX IF NOT EXISTS idx_document_provider ON document(provider);
                """,
                down_sql="""
                    DROP INDEX IF EXISTS idx_document_provider;
                    DROP INDEX IF EXISTS idx_task_due_date;
                    DROP INDEX IF EXISTS idx_task_status;
                    DROP INDEX IF EXISTS idx_practitioner_email;
                    DROP INDEX IF EXISTS idx_practitioner_provider;
                    DROP INDEX IF EXISTS idx_order_item_order_id;
                    DROP INDEX IF EXISTS idx_order_created_at;
                    DROP INDEX IF EXISTS idx_order_status;
                    DROP INDEX IF EXISTS idx_order_provider;
                    DROP INDEX IF EXISTS idx_stock_unit_barcode;
                    DROP INDEX IF EXISTS idx_stock_unit_status;
                    DROP INDEX IF EXISTS idx_stock_unit_item_id;
                    DROP INDEX IF EXISTS idx_stock_item_name;
                    DROP INDEX IF EXISTS idx_stock_item_provider;
                """
            ),
            Migration(
                version="003",
                description="Add audit trail tables",
                up_sql="""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        table_name VARCHAR(50) NOT NULL,
                        record_id INTEGER NOT NULL,
                        action VARCHAR(10) NOT NULL,
                        old_values TEXT,
                        new_values TEXT,
                        user_id VARCHAR(100),
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON audit_log(table_name, record_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
                """,
                down_sql="""
                    DROP INDEX IF EXISTS idx_audit_log_user_id;
                    DROP INDEX IF EXISTS idx_audit_log_timestamp;
                    DROP INDEX IF EXISTS idx_audit_log_table_record;
                    DROP TABLE IF EXISTS audit_log;
                """
            ),
            Migration(
                version="004",
                description="Add API tokens table",
                up_sql="""
                    CREATE TABLE IF NOT EXISTS api_token (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_hash VARCHAR(255) UNIQUE NOT NULL,
                        user_id VARCHAR(100) NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        permissions TEXT,
                        expires_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_used_at DATETIME
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_api_token_user_id ON api_token(user_id);
                    CREATE INDEX IF NOT EXISTS idx_api_token_expires_at ON api_token(expires_at);
                """,
                down_sql="""
                    DROP INDEX IF EXISTS idx_api_token_expires_at;
                    DROP INDEX IF EXISTS idx_api_token_user_id;
                    DROP TABLE IF EXISTS api_token;
                """
            ),
            Migration(
                version="005",
                description="Add notification system",
                up_sql="""
                    CREATE TABLE IF NOT EXISTS notification (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id VARCHAR(100) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        message TEXT NOT NULL,
                        type VARCHAR(50) DEFAULT 'info',
                        read_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_notification_user_id ON notification(user_id);
                    CREATE INDEX IF NOT EXISTS idx_notification_read_at ON notification(read_at);
                    CREATE INDEX IF NOT EXISTS idx_notification_created_at ON notification(created_at);
                """,
                down_sql="""
                    DROP INDEX IF EXISTS idx_notification_created_at;
                    DROP INDEX IF EXISTS idx_notification_read_at;
                    DROP INDEX IF EXISTS idx_notification_user_id;
                    DROP TABLE IF EXISTS notification;
                """
            ),
            Migration(
                version="006",
                description="Add Fillout integration field to orders",
                up_sql="""
                    ALTER TABLE "order" ADD COLUMN fillout_submission_id VARCHAR(100);
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_order_fillout_submission_id ON "order"(fillout_submission_id);
                """,
                down_sql="""
                    DROP INDEX IF EXISTS idx_order_fillout_submission_id;
                    ALTER TABLE "order" DROP COLUMN fillout_submission_id;
                """
            ),
            Migration(
                version="007",
                description="Add file storage columns to document table for database storage",
                up_sql="""
                    -- Add columns as nullable for backward compatibility with existing records
                    -- SQLite: ALTER TABLE ADD COLUMN doesn't support NOT NULL without DEFAULT
                    -- PostgreSQL: BYTEA for binary data
                    ALTER TABLE document ADD COLUMN file_data BLOB;
                    ALTER TABLE document ADD COLUMN file_size INTEGER;
                    ALTER TABLE document ADD COLUMN content_type VARCHAR(100);
                    -- Note: Existing records will have NULL values, new uploads will have data
                """,
                down_sql="""
                    ALTER TABLE document DROP COLUMN content_type;
                    ALTER TABLE document DROP COLUMN file_size;
                    ALTER TABLE document DROP COLUMN file_data;
                """
            ),
            Migration(
                version="008",
                description="Remove unique constraint from stock_unit.barcode to allow duplicate barcodes",
                up_sql="""
                    -- Drop unique constraint/index on barcode column
                    -- PostgreSQL: Drop constraint (may be named stock_unit_barcode_key or similar)
                    DO $$
                    DECLARE
                        constraint_name text;
                    BEGIN
                        -- Find and drop the unique constraint
                        SELECT conname INTO constraint_name
                        FROM pg_constraint
                        WHERE conrelid = 'stock_unit'::regclass
                        AND contype = 'u'
                        AND array_length(conkey, 1) = 1
                        AND (SELECT attname FROM pg_attribute WHERE attrelid = 'stock_unit'::regclass AND attnum = conkey[1]) = 'barcode';
                        
                        IF constraint_name IS NOT NULL THEN
                            EXECUTE 'ALTER TABLE stock_unit DROP CONSTRAINT ' || quote_ident(constraint_name);
                        END IF;
                    END $$;
                    
                    -- Also drop any unique index on barcode
                    DROP INDEX IF EXISTS stock_unit_barcode_key;
                    DROP INDEX IF EXISTS idx_stock_unit_barcode_unique;
                """,
                down_sql="""
                    -- Restore unique constraint (recreate table with UNIQUE)
                    CREATE TABLE IF NOT EXISTS stock_unit_old (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        barcode VARCHAR(120) UNIQUE NOT NULL,
                        batch_number VARCHAR(120),
                        status VARCHAR(40) NOT NULL DEFAULT 'In Stock',
                        item_id INTEGER NOT NULL,
                        last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (item_id) REFERENCES stock_item (id)
                    );
                    
                    -- Copy data (may fail if duplicates exist)
                    INSERT INTO stock_unit_old (id, barcode, batch_number, status, item_id, last_update)
                    SELECT id, barcode, batch_number, status, item_id, last_update FROM stock_unit;
                    
                    DROP TABLE stock_unit;
                    ALTER TABLE stock_unit_old RENAME TO stock_unit;
                    
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_item_id ON stock_unit(item_id);
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_status ON stock_unit(status);
                    CREATE INDEX IF NOT EXISTS idx_stock_unit_barcode ON stock_unit(barcode);
                """
            )
        ]
        
        self.migrations = migrations
    
    def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        try:
            with self.db.engine.connect() as conn:
                result = conn.execute(text("SELECT version FROM migrations ORDER BY version"))
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Failed to get applied migrations: {e}")
            return []
    
    def get_pending_migrations(self) -> List[Migration]:
        """Get list of pending migrations."""
        applied = self.get_applied_migrations()
        return [m for m in self.migrations if m.version not in applied]
    
    def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration."""
        try:
            with self.db.engine.connect() as conn:
                # Execute migration SQL
                conn.execute(text(migration.up_sql))
                
                # Record migration
                conn.execute(text("""
                    INSERT INTO migrations (version, description, applied_at)
                    VALUES (:version, :description, :applied_at)
                """), {
                    'version': migration.version,
                    'description': migration.description,
                    'applied_at': datetime.utcnow()
                })
                
                conn.commit()
                logger.info(f"Applied migration {migration.version}: {migration.description}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to apply migration {migration.version}: {e}")
            return False
    
    def rollback_migration(self, migration: Migration) -> bool:
        """Rollback a single migration."""
        if not migration.down_sql:
            logger.warning(f"No rollback SQL for migration {migration.version}")
            return False
        
        try:
            with self.db.engine.connect() as conn:
                # Execute rollback SQL
                conn.execute(text(migration.down_sql))
                
                # Remove migration record
                conn.execute(text("DELETE FROM migrations WHERE version = :version"), {
                    'version': migration.version
                })
                
                conn.commit()
                logger.info(f"Rolled back migration {migration.version}: {migration.description}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to rollback migration {migration.version}: {e}")
            return False
    
    def migrate(self) -> bool:
        """Apply all pending migrations."""
        pending = self.get_pending_migrations()
        
        if not pending:
            logger.info("No pending migrations")
            return True
        
        logger.info(f"Applying {len(pending)} pending migrations")
        
        for migration in pending:
            if not self.apply_migration(migration):
                logger.error(f"Migration failed at {migration.version}")
                return False
        
        logger.info("All migrations applied successfully")
        return True
    
    def rollback_to(self, target_version: str) -> bool:
        """Rollback to a specific migration version."""
        applied = self.get_applied_migrations()
        
        if target_version not in applied:
            logger.error(f"Target version {target_version} not found in applied migrations")
            return False
        
        # Find migrations to rollback (in reverse order)
        migrations_to_rollback = []
        for migration in reversed(self.migrations):
            if migration.version in applied and migration.version > target_version:
                migrations_to_rollback.append(migration)
        
        logger.info(f"Rolling back {len(migrations_to_rollback)} migrations to version {target_version}")
        
        for migration in migrations_to_rollback:
            if not self.rollback_migration(migration):
                logger.error(f"Rollback failed at {migration.version}")
                return False
        
        logger.info(f"Successfully rolled back to version {target_version}")
        return True
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get migration status information."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()
        
        return {
            'applied_count': len(applied),
            'pending_count': len(pending),
            'applied_migrations': applied,
            'pending_migrations': [m.version for m in pending],
            'total_migrations': len(self.migrations)
        }
    
    def create_migration(self, version: str, description: str, up_sql: str, down_sql: str = "") -> Migration:
        """Create a new migration."""
        migration = Migration(version, description, up_sql, down_sql)
        self.migrations.append(migration)
        return migration


def init_migrations(db: SQLAlchemy) -> MigrationManager:
    """Initialize migration manager."""
    return MigrationManager(db)


def run_migrations(db: SQLAlchemy) -> bool:
    """Run all pending migrations."""
    manager = MigrationManager(db)
    return manager.migrate()


def get_migration_status(db: SQLAlchemy) -> Dict[str, Any]:
    """Get migration status."""
    manager = MigrationManager(db)
    return manager.get_migration_status()



