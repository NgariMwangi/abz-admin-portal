#!/usr/bin/env python3
"""
Test script to verify profit calculation logic

This script tests the profit calculation formulas to ensure they work correctly.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import Order, OrderItem, Product, User, Branch, OrderType
from extensions import db
from sqlalchemy import func, and_
from datetime import datetime, timedelta

def test_profit_calculation():
    """Test the profit calculation logic"""
    with app.app_context():
        try:
            print("🧮 Testing Profit Calculation Logic...")
            print("=" * 50)
            
            # Get current month
            now = datetime.now()
            this_month = now.replace(day=1).date()
            
            # Test total profit calculation
            print("\n📊 Total Profit Calculation:")
            print("-" * 30)
            
            # Calculate total revenue from approved orders
            total_revenue = db.session.query(func.sum(OrderItem.final_price * OrderItem.quantity)).join(
                Order, OrderItem.orderid == Order.id
            ).filter(Order.approvalstatus == True).scalar() or 0
            
            print(f"Total Revenue: KSh {total_revenue:,.2f}")
            
            # Calculate total cost of goods sold
            total_cogs = db.session.query(func.sum(OrderItem.buying_price * OrderItem.quantity)).join(
                Order, OrderItem.orderid == Order.id
            ).filter(Order.approvalstatus == True).scalar() or 0
            
            print(f"Total COGS: KSh {total_cogs:,.2f}")
            
            # Calculate total profit
            total_profit = total_revenue - total_cogs
            print(f"Total Profit: KSh {total_profit:,.2f}")
            
            # Test monthly profit calculation
            print("\n📅 Monthly Profit Calculation:")
            print("-" * 30)
            
            # Calculate monthly revenue
            monthly_revenue = db.session.query(func.sum(OrderItem.final_price * OrderItem.quantity)).join(
                Order, OrderItem.orderid == Order.id
            ).filter(
                and_(Order.approvalstatus == True, Order.created_at >= this_month)
            ).scalar() or 0
            
            print(f"Monthly Revenue: KSh {monthly_revenue:,.2f}")
            
            # Calculate monthly cost of goods sold
            monthly_cogs = db.session.query(func.sum(OrderItem.buying_price * OrderItem.quantity)).join(
                Order, OrderItem.orderid == Order.id
            ).filter(
                and_(Order.approvalstatus == True, Order.created_at >= this_month)
            ).scalar() or 0
            
            print(f"Monthly COGS: KSh {monthly_cogs:,.2f}")
            
            # Calculate monthly profit
            monthly_profit = monthly_revenue - monthly_cogs
            print(f"Monthly Profit: KSh {monthly_profit:,.2f}")
            
            # Calculate profit margin
            print("\n📈 Profit Margin Calculation:")
            print("-" * 30)
            
            if total_revenue > 0:
                profit_margin = (total_profit / total_revenue) * 100
                print(f"Profit Margin: {profit_margin:.2f}%")
            else:
                print("Profit Margin: 0.00% (No revenue)")
            
            # Show sample order items for verification
            print("\n🔍 Sample Order Items (for verification):")
            print("-" * 40)
            
            sample_items = db.session.query(OrderItem).join(Order).filter(
                Order.approvalstatus == True
            ).limit(5).all()
            
            for i, item in enumerate(sample_items, 1):
                print(f"Item {i}:")
                print(f"  Product: {item.product.name if item.product else 'N/A'}")
                print(f"  Quantity: {item.quantity}")
                print(f"  Final Price: KSh {item.final_price or 0:,.2f}")
                print(f"  Buying Price: KSh {item.buying_price or 0:,.2f}")
                print(f"  Revenue: KSh {(item.final_price or 0) * item.quantity:,.2f}")
                print(f"  COGS: KSh {(item.buying_price or 0) * item.quantity:,.2f}")
                print(f"  Profit: KSh {((item.final_price or 0) - (item.buying_price or 0)) * item.quantity:,.2f}")
                print()
            
            # Summary
            print("✅ Profit calculation test completed!")
            print(f"📊 Summary:")
            print(f"  - Total Revenue: KSh {total_revenue:,.2f}")
            print(f"  - Total COGS: KSh {total_cogs:,.2f}")
            print(f"  - Total Profit: KSh {total_profit:,.2f}")
            print(f"  - Monthly Revenue: KSh {monthly_revenue:,.2f}")
            print(f"  - Monthly COGS: KSh {monthly_cogs:,.2f}")
            print(f"  - Monthly Profit: KSh {monthly_profit:,.2f}")
            
            if total_revenue > 0:
                print(f"  - Profit Margin: {(total_profit / total_revenue) * 100:.2f}%")
            
        except Exception as e:
            print(f"❌ Error in profit calculation test: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_profit_calculation()





