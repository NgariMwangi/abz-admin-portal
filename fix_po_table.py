#!/usr/bin/env python3
"""
Script to manually create the purchase_order_items table with the correct schema
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from extensions import db
from sqlalchemy import text

def fix_po_items_table():
    with app.app_context():
        try:
            print("Dropping existing purchase_order_items table...")
            db.session.execute(text("DROP TABLE IF EXISTS purchase_order_items CASCADE"))
            db.session.commit()
            print("✅ Table dropped successfully")
            
            print("Creating purchase_order_items table with correct schema...")
            
            # Create table with all required columns
            create_table_sql = """
            CREATE TABLE purchase_order_items (
                id SERIAL PRIMARY KEY,
                purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
                product_code VARCHAR NOT NULL,
                product_name VARCHAR,
                quantity INTEGER NOT NULL,
                unit_price NUMERIC(10,2),
                total_price NUMERIC(10,2),
                received_quantity INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            db.session.execute(text(create_table_sql))
            db.session.commit()
            print("✅ Table created successfully with correct schema")
            
            # Verify the new table structure
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            if 'purchase_order_items' in inspector.get_table_names():
                columns = inspector.get_columns('purchase_order_items')
                print("\nNew PurchaseOrderItem table columns:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']} (nullable: {col['nullable']})")
            else:
                print("❌ Table was not created!")
                return
                
        except Exception as e:
            print(f"Error fixing table: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()

if __name__ == "__main__":
    fix_po_items_table()

