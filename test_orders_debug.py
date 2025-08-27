#!/usr/bin/env python3
"""
Script to debug orders data and total calculations
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import Order, OrderItem, Product, User, Branch, OrderType
from extensions import db
from decimal import Decimal

def debug_orders():
    with app.app_context():
        try:
            print("🔍 Debugging Orders Data...")
            
            # Check if we have any orders
            order_count = Order.query.count()
            print(f"Total orders in database: {order_count}")
            
            if order_count == 0:
                print("❌ No orders found in database!")
                return
            
            # Get the first few orders
            orders = Order.query.limit(3).all()
            
            for i, order in enumerate(orders, 1):
                print(f"\n--- Order {i} ---")
                print(f"Order ID: {order.id}")
                print(f"User ID: {order.userid}")
                print(f"Branch ID: {order.branchid}")
                print(f"Order Type ID: {order.ordertypeid}")
                print(f"Approval Status: {order.approvalstatus}")
                print(f"Payment Status: {order.payment_status}")
                print(f"Created At: {order.created_at}")
                
                # Check relationships
                try:
                    user = order.user
                    print(f"✅ User: {user.firstname} {user.lastname} ({user.email})")
                except Exception as e:
                    print(f"❌ User relationship error: {e}")
                
                try:
                    branch = order.branch
                    print(f"✅ Branch: {branch.name} ({branch.location})")
                except Exception as e:
                    print(f"❌ Branch relationship error: {e}")
                
                try:
                    ordertype = order.ordertype
                    print(f"✅ Order Type: {ordertype.name}")
                except Exception as e:
                    print(f"❌ Order Type relationship error: {e}")
                
                # Check order items
                try:
                    items = order.order_items
                    print(f"Order Items: {len(items)} items")
                    
                    total_amount = 0
                    for j, item in enumerate(items, 1):
                        print(f"  Item {j}:")
                        print(f"    Product ID: {item.productid}")
                        print(f"    Quantity: {item.quantity}")
                        print(f"    Final Price: {item.final_price}")
                        print(f"    Original Price: {item.original_price}")
                        print(f"    Negotiated Price: {item.negotiated_price}")
                        
                        # Check product relationship
                        try:
                            product = item.product
                            print(f"    ✅ Product: {product.name}")
                            print(f"    Product Selling Price: {product.sellingprice}")
                            
                            # Calculate item total
                            if item.final_price:
                                item_total = item.final_price * item.quantity
                                total_amount += item_total
                                print(f"    Item Total (final_price): {item_total}")
                            elif product.sellingprice:
                                item_total = product.sellingprice * item.quantity
                                total_amount += item_total
                                print(f"    Item Total (sellingprice): {item_total}")
                            else:
                                print(f"    ❌ No price available for item")
                        except Exception as e:
                            print(f"    ❌ Product relationship error: {e}")
                    
                    print(f"  📊 Calculated Total: {total_amount}")
                    
                    # Store calculated total on order object
                    order.calculated_total = total_amount
                    
                except Exception as e:
                    print(f"❌ Order items error: {e}")
                
                print("-" * 50)
            
            # Test the calculation logic
            print("\n🧮 Testing Calculation Logic...")
            for order in orders:
                if hasattr(order, 'calculated_total'):
                    print(f"Order {order.id}: {order.calculated_total}")
                else:
                    print(f"Order {order.id}: No calculated_total attribute")
            
        except Exception as e:
            print(f"❌ Error in debug_orders: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_orders()



