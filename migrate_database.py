#!/usr/bin/env python3
"""
Database migration script to add image_url to categories and create sub_category table
"""

from flask import Flask
from config import Config
from extensions import db
from models import Category, SubCategory, ProductDescription
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def migrate_database():
    with app.app_context():
        try:
            print("🔄 Starting database migration...")
            
            # Check if image_url column exists in category table
            print("📋 Checking category table structure...")
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'category' AND column_name = 'image_url'
            """))
            
            if not result.fetchone():
                print("➕ Adding image_url column to category table...")
                db.session.execute(text("ALTER TABLE category ADD COLUMN image_url VARCHAR"))
                print("✅ image_url column added to category table")
            else:
                print("✅ image_url column already exists in category table")
            
            # Check if sub_category table exists
            print("📋 Checking if sub_category table exists...")
            result = db.session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'sub_category'
            """))
            
            if not result.fetchone():
                print("➕ Creating sub_category table...")
                db.session.execute(text("""
                    CREATE TABLE sub_category (
                        id SERIAL PRIMARY KEY,
                        category_id INTEGER NOT NULL REFERENCES category(id),
                        name VARCHAR NOT NULL,
                        description VARCHAR,
                        image_url VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("✅ sub_category table created")
            else:
                print("✅ sub_category table already exists")
            
            # Check if subcategory_id column exists in products table
            print("📋 Checking products table structure...")
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'products' AND column_name = 'subcategory_id'
            """))
            
            if not result.fetchone():
                print("➕ Adding subcategory_id column to products table...")
                db.session.execute(text("ALTER TABLE products ADD COLUMN subcategory_id INTEGER REFERENCES sub_category(id)"))
                print("✅ subcategory_id column added to products table")
            else:
                print("✅ subcategory_id column already exists in products table")
            
            # Check if product_descriptions table exists
            print("📋 Checking if product_descriptions table exists...")
            result = db.session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'product_descriptions'
            """))
            
            if not result.fetchone():
                print("➕ Creating product_descriptions table...")
                db.session.execute(text("""
                    CREATE TABLE product_descriptions (
                        id SERIAL PRIMARY KEY,
                        product_id INTEGER NOT NULL REFERENCES products(id),
                        title VARCHAR NOT NULL,
                        content TEXT NOT NULL,
                        content_type VARCHAR DEFAULT 'text',
                        language VARCHAR DEFAULT 'en',
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("✅ product_descriptions table created")
            else:
                print("✅ product_descriptions table already exists")
            
            # Add expenses table
            print("📋 Checking if expenses table exists...")
            result = db.session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'expenses'
            """))
            
            if not result.fetchone():
                print("➕ Creating expenses table...")
                db.session.execute(text("""
                    CREATE TABLE expenses (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR NOT NULL,
                        description TEXT,
                        amount DECIMAL(10,2) NOT NULL,
                        category VARCHAR NOT NULL,
                        expense_date DATE NOT NULL,
                        payment_method VARCHAR,
                        receipt_url VARCHAR,
                        branch_id INTEGER,
                        user_id INTEGER NOT NULL,
                        approved_by INTEGER,
                        status VARCHAR DEFAULT 'pending',
                        approval_notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (branch_id) REFERENCES branch (id),
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        FOREIGN KEY (approved_by) REFERENCES users (id)
                    )
                """))
                print("✅ expenses table created")
            else:
                print("✅ expenses table already exists")
            
            db.session.commit()
            print("🎉 Database migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    migrate_database() 