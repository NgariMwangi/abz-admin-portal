#!/usr/bin/env python3
"""
Script to add test data to the purchase_order_items table
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import PurchaseOrder, PurchaseOrderItem
from extensions import db
from sqlalchemy import text

def add_test_po_data():
    with app.app_context():
        try:
            # Check if we have any purchase orders
            po_count = PurchaseOrder.query.count()
            print(f"Found {po_count} purchase orders")
            
            if po_count == 0:
                print("No purchase orders found. Please create a purchase order first.")
                return
            
            # Get the first purchase order
            po = PurchaseOrder.query.first()
            print(f"Using purchase order: {po.po_number}")
            
            # Check if we already have items
            existing_items = PurchaseOrderItem.query.filter_by(purchase_order_id=po.id).count()
            print(f"Found {existing_items} existing items")
            
            if existing_items == 0:
                # Add a test item
                test_item = PurchaseOrderItem(
                    purchase_order_id=po.id,
                    product_code="TEST001",
                    product_name="Test Product",
                    quantity=5,
                    unit_price=None,
                    total_price=None,
                    received_quantity=0,
                    notes="Test item for verification"
                )
                
                db.session.add(test_item)
                db.session.commit()
                print("✅ Test item added successfully")
            else:
                print("Items already exist, skipping")
            
            # Verify the data
            items = PurchaseOrderItem.query.filter_by(purchase_order_id=po.id).all()
            print(f"\nCurrent items in PO {po.po_number}:")
            for item in items:
                print(f"  - {item.product_code}: {item.product_name} (Qty: {item.quantity})")
                
        except Exception as e:
            print(f"Error adding test data: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()

if __name__ == "__main__":
    add_test_po_data()

