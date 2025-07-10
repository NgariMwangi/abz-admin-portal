from extensions import db
from models import User
from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    print("=== Current Users in Database ===")
    users = User.query.all()
    
    if not users:
        print("No users found in database!")
        print("\nCreating admin user...")
        
        # Create admin user
        admin_user = User(
            email='admin@abz.com',
            firstname='Admin',
            lastname='User',
            password='admin123',
            role='admin'
        )
        
        db.session.add(admin_user)
        db.session.commit()
        print("✅ Admin user created successfully!")
        print("Email: admin@abz.com")
        print("Password: admin123")
        print("Role: admin")
    else:
        print(f"Found {len(users)} user(s):")
        for user in users:
            print(f"ID: {user.id}")
            print(f"Name: {user.firstname} {user.lastname}")
            print(f"Email: {user.email}")
            print(f"Role: {user.role}")
            print(f"Created: {user.created_at}")
            print("-" * 30)
    
    print("\n=== Role Summary ===")
    admin_count = User.query.filter_by(role='admin').count()
    sales_count = User.query.filter_by(role='sales').count()
    customer_count = User.query.filter_by(role='customer').count()
    
    print(f"Admins: {admin_count}")
    print(f"Sales: {sales_count}")
    print(f"Customers: {customer_count}")
    
    if admin_count == 0:
        print("\n⚠️  WARNING: No admin users found!")
        print("You need at least one admin user to access the user management features.")
        print("Run this script again to create an admin user.") 