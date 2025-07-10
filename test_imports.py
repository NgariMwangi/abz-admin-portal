#!/usr/bin/env python3

print("Testing imports...")

try:
    from extensions import db
    print("✅ extensions import successful")
except Exception as e:
    print(f"❌ extensions import failed: {e}")

try:
    from models import User, Branch, Category, Product
    print("✅ models import successful")
except Exception as e:
    print(f"❌ models import failed: {e}")

try:
    from flask import Flask
    from config import Config
    from extensions import db
    
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    from models import User, Branch, Category, Product
    
    with app.app_context():
        users = User.query.all()
        print(f"✅ Database query successful - found {len(users)} users")
        
except Exception as e:
    print(f"❌ Full application test failed: {e}")

print("Import test completed!") 