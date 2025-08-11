#!/usr/bin/env python3
"""
Script to recreate the purchase_order_items table with the correct schema
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import PurchaseOrderItem
from extensions import db
from sqlalchemy import text

def recreate_po_items_table():
    with app.app_context():
        try:
            print("Dropping existing purchase_order_items table...")
            db.session.execute(text("DROP TABLE IF EXISTS purchase_order_items CASCADE"))
            db.session.commit()
            print("✅ Table dropped successfully")
            
            print("Recreating purchase_order_items table...")
            db.create_all()
            print("✅ Table recreated successfully")
            
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
            print(f"Error recreating table: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()

if __name__ == "__main__":
    recreate_po_items_table()

