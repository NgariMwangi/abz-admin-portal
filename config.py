import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'abz-hardware-secret-key-2024-secure-random-string'
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:deno0707@localhost/abzone'
    # SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:%23Deno0707@69.197.187.23:5432/abzone'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Cloudinary Configuration
    # Use environment variables if available, otherwise use placeholder values
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dxyewzvnr')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '171127627627327')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'zgKkOpX35l93D7CdwnWOWGF2mk8')
    
    # File Upload Configuration
    UPLOAD_FOLDER = 'static/uploads/products'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'heic', 'heif'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Session Configuration
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # 24 hour session lifetime 