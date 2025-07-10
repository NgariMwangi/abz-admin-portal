#!/usr/bin/env python3
"""
Test script to check if the users route works properly
"""

from main import app, db
from models import User
from flask_login import login_user
from datetime import datetime

def test_users_route():
    with app.app_context():
        try:
            # Check if User table exists
            print("Checking if User table exists...")
            users = User.query.all()
            print(f"Found {len(users)} users in database")
            
            # Check if there are any users
            if len(users) == 0:
                print("No users found in database. Creating a test user...")
                test_user = User(
                    email='test@example.com',
                    firstname='Test',
                    lastname='User',
                    password='password123',
                    role='admin',
                    created_at=datetime.utcnow()
                )
                db.session.add(test_user)
                db.session.commit()
                print("Test user created successfully")
            
            # Test pagination
            print("Testing pagination...")
            pagination = User.query.paginate(page=1, per_page=10, error_out=False)
            print(f"Pagination: page {pagination.page}, total {pagination.total}, pages {pagination.pages}")
            
            print("✅ Users route test completed successfully")
            
        except Exception as e:
            print(f"❌ Error in users route test: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_users_route() 