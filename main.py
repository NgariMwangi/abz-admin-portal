from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
import csv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO, StringIO
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy.exc import IntegrityError
import cloudinary
import cloudinary.uploader
import cloudinary.api
from werkzeug.utils import secure_filename
import os
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import joinedload

from extensions import db

app = Flask(__name__)
app.config.from_object(Config)

# Add session debugging
print(f"🔍 Session configuration:")
print(f"   - SECRET_KEY set: {'Yes' if app.config.get('SECRET_KEY') else 'No'}")
print(f"   - SESSION_COOKIE_SECURE: {app.config.get('SESSION_COOKIE_SECURE', 'Not set')}")
print(f"   - SESSION_COOKIE_HTTPONLY: {app.config.get('SESSION_COOKIE_HTTPONLY', 'Not set')}")

# Cloudinary Configuration
cloudinary.config(
    cloud_name = app.config['CLOUDINARY_CLOUD_NAME'],
    api_key = app.config['CLOUDINARY_API_KEY'],
    api_secret = app.config['CLOUDINARY_API_SECRET']
)

# Initialize SQLAlchemy with the app
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Custom template filter for formatting stock numbers
@app.template_filter('format_stock')
def format_stock(value):
    """Format stock numbers without unnecessary decimal places."""
    if value is None:
        return '0'
    
    # Convert to float to handle any type
    try:
        num = float(value)
        # If it's a whole number, return as integer
        if num == int(num):
            return str(int(num))
        else:
            # If it has decimals, format to remove trailing zeros
            return f"{num:g}"
    except (ValueError, TypeError):
        return str(value)

# Import models after db is initialized
from models import Branch, Category, User, OrderType, Order, OrderItem, StockTransaction, Payment, SubCategory, ProductDescription, Expense, Supplier, PurchaseOrder, PurchaseOrderItem, ProductCatalog, BranchProduct, Quotation, QuotationItem

# Define EAT timezone
EAT = timezone(timedelta(hours=3))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    print("✅ All tables created successfully in PostgreSQL.")

# Custom decorator for role-based access
def role_required(roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login', next=request.url))
            if not hasattr(current_user, 'role') or current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                # Redirect to a safe page instead of index to avoid potential loops
                return redirect(url_for('unauthorized'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

@app.route("/")
@login_required
@role_required(['admin']) 
def index():
    print(f"🔍 Index route accessed - User: {current_user.email if current_user.is_authenticated else 'Not authenticated'}")
    print(f"🔍 User role: {current_user.role if current_user.is_authenticated else 'No role'}")
    
    # Set default date values
    today = datetime.now().date()
    this_month = datetime.now().replace(day=1).date()
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    
    try:
        # Get real business data in EAT timezone
        now = datetime.now(EAT)
        today = now.date()
        this_month = now.replace(day=1).date()
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        print(f"✅ EAT timezone calculation successful")
    except Exception as e:
        print(f"❌ Error in index route setup: {e}")
        flash('An error occurred while loading dashboard data. Please try again.', 'error')
        # Continue with default date values
    
    # Dashboard statistics
    try:
        total_users = User.query.count()
        total_products = BranchProduct.query.count()
        total_orders = Order.query.count()
        total_branches = Branch.query.count()
    except Exception as e:
        print(f"Error getting basic statistics: {e}")
        total_users = 0
        total_products = 0
        total_orders = 0
        total_branches = 0
    
    # Total product asset value (buying price * stock quantity)
    # Exclude products with no buying price, zero stock, or null stock
    try:
        total_product_asset = db.session.query(
            func.sum(BranchProduct.buyingprice * BranchProduct.stock)
        ).filter(
            and_(
                BranchProduct.buyingprice.isnot(None),  # Exclude products with no buying price
                BranchProduct.buyingprice > 0,          # Exclude products with zero buying price
                BranchProduct.stock.isnot(None),        # Exclude products with null stock
                BranchProduct.stock > 0                 # Exclude products with zero stock
            )
        ).scalar() or 0
    except Exception as e:
        print(f"Error calculating total product asset: {e}")
        total_product_asset = 0
    
    # ProductCatalog asset statistics
    try:
        products_with_assets = db.session.query(BranchProduct).filter(
            and_(
                BranchProduct.buyingprice.isnot(None),
                BranchProduct.buyingprice > 0,
                BranchProduct.stock.isnot(None),
                BranchProduct.stock > 0
            )
        ).count()
        
        products_without_buying_price = db.session.query(BranchProduct).filter(
            or_(
                BranchProduct.buyingprice.is_(None),
                BranchProduct.buyingprice == 0
            )
        ).count()
        
        products_with_zero_stock = db.session.query(BranchProduct).filter(
            or_(
                BranchProduct.stock.is_(None),
                BranchProduct.stock == 0
            )
        ).count()
    except Exception as e:
        print(f"Error getting product asset statistics: {e}")
        products_with_assets = 0
        products_without_buying_price = 0
        products_with_zero_stock = 0
    
    # Average asset value per product (excluding products without assets)
    avg_asset_per_product = total_product_asset / products_with_assets if products_with_assets > 0 else 0
    
    # Recent orders (last 7 days)
    try:
        recent_orders = Order.query.filter(
            Order.created_at >= today - timedelta(days=7)
        ).count()
    except Exception as e:
        print(f"Error getting recent orders count: {e}")
        recent_orders = 0
    
    # Pending orders
    try:
        pending_orders = Order.query.filter_by(approvalstatus=False).count()
    except Exception as e:
        print(f"Error getting pending orders count: {e}")
        pending_orders = 0
    
    # Total revenue (from completed payments)
    try:
        total_revenue = db.session.query(func.sum(Payment.amount)).join(
            Order, Payment.orderid == Order.id
        ).filter(Payment.payment_status == 'completed').scalar() or 0
    except Exception as e:
        print(f"Error calculating total revenue: {e}")
        total_revenue = 0
    
    # Monthly revenue (from completed payments)
    try:
        monthly_revenue = db.session.query(func.sum(Payment.amount)).join(
            Order, Payment.orderid == Order.id
        ).filter(
            and_(Payment.payment_status == 'completed', Payment.created_at >= this_month)
        ).scalar() or 0
    except Exception as e:
        print(f"Error calculating monthly revenue: {e}")
        monthly_revenue = 0
    
    # Total profit calculation (Revenue - Cost of Goods Sold)
    try:
        # Calculate total profit from completed payments
        total_profit = db.session.query(func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity)).join(
            Order, OrderItem.orderid == Order.id
        ).join(
            Payment, Order.id == Payment.orderid
        ).filter(
            Payment.payment_status == 'completed',
            OrderItem.final_price.isnot(None),
            OrderItem.buying_price.isnot(None)
        ).scalar() or 0
        
        # Calculate total cost of goods sold for completed payments
        total_cogs = db.session.query(func.sum(OrderItem.buying_price * OrderItem.quantity)).join(
            Order, OrderItem.orderid == Order.id
        ).join(
            Payment, Order.id == Payment.orderid
        ).filter(
            Payment.payment_status == 'completed',
            OrderItem.buying_price.isnot(None)
        ).scalar() or 0
        
    except Exception as e:
        print(f"Error calculating total profit: {e}")
        total_profit = 0
        total_cogs = 0
    
    # Monthly profit calculation
    try:
        # Calculate monthly profit from completed payments
        monthly_profit = db.session.query(func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity)).join(
            Order, OrderItem.orderid == Order.id
        ).join(
            Payment, Order.id == Payment.orderid
        ).filter(
            and_(Payment.payment_status == 'completed', Payment.created_at >= this_month),
            OrderItem.final_price.isnot(None),
            OrderItem.buying_price.isnot(None)
        ).scalar() or 0
        
        # Calculate monthly cost of goods sold for completed payments
        monthly_cogs = db.session.query(func.sum(OrderItem.buying_price * OrderItem.quantity)).join(
            Order, OrderItem.orderid == Order.id
        ).join(
            Payment, Order.id == Payment.orderid
        ).filter(
            and_(Payment.payment_status == 'completed', Payment.created_at >= this_month),
            OrderItem.buying_price.isnot(None)
        ).scalar() or 0
        
    except Exception as e:
        print(f"Error calculating monthly profit: {e}")
        monthly_profit = 0
        monthly_cogs = 0
    
    # Low stock products (less than 10 items)
    try:
        low_stock_products = BranchProduct.query.filter(BranchProduct.stock < 10).count()
    except Exception as e:
        print(f"Error getting low stock products count: {e}")
        low_stock_products = 0
    
    # Recent activities - Load recent orders with proper relationships and calculate totals
    try:
        recent_orders_list = db.session.query(Order).options(
            db.joinedload(Order.user),
            db.joinedload(Order.branch),
            db.joinedload(Order.order_items).joinedload(OrderItem.branch_product).joinedload(BranchProduct.catalog_product)
        ).order_by(Order.created_at.desc()).limit(5).all()
        
        # Calculate totals for each recent order
        for order in recent_orders_list:
            total_amount = 0
            for item in order.order_items:
                # Handle both cases: products with relationships and manually entered items
                if item.final_price:
                    # Use the final_price if available (for manually entered items or negotiated prices)
                    item_total = item.final_price * item.quantity
                    total_amount += item_total
                elif item.branch_product and item.branch_product.sellingprice:
                    # Use branch product's selling price if no final_price but branch_product relationship exists
                    item_total = item.branch_product.sellingprice * item.quantity
                    total_amount += item_total
                elif hasattr(item, 'product_name') and item.product_name and item.original_price:
                    # For manually entered items without product relationship, check if they have a price
                    item_total = item.original_price * item.quantity
                    total_amount += item_total
            
            # Store the calculated total on the order object for template use
            order.calculated_total = total_amount
            
            # Calculate profit for the order using OrderItem fields directly
            order_profit = 0
            print(f"🔍 Dashboard: Calculating profit for order {order.id} with {len(order.order_items)} items")
            for item in order.order_items:
                print(f"  📦 Dashboard Item {item.id}: final_price={item.final_price}, buying_price={item.buying_price}")
                
                # Use final_price as selling price and buying_price from OrderItem table
                if item.final_price and item.buying_price:
                    item_profit = (item.final_price - item.buying_price) * item.quantity
                    order_profit += item_profit
                    print(f"    💰 Profit: ({item.final_price} - {item.buying_price}) × {item.quantity} = {item_profit}")
                else:
                    print(f"    ⚠️ Cannot calculate profit - missing price data")
                    print(f"      final_price: {item.final_price}")
                    print(f"      buying_price: {item.buying_price}")
            
            # Store the calculated profit on the order object for template use
            order.calculated_profit = order_profit
            print(f"🔍 Dashboard: Order {order.id}: calculated_profit = {order_profit}")
        
        # Add adjusted times (3 hours ahead) for display
        for order in recent_orders_list:
            order.created_at_adjusted = order.created_at + timedelta(hours=3)
        
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    except Exception as e:
        print(f"Error getting recent activities: {e}")
        recent_orders_list = []
        recent_users = []
    
    # Branch statistics
    branch_stats = []
    try:
        for branch in Branch.query.all():
            try:
                branch_products = BranchProduct.query.filter_by(branchid=branch.id).count()
                branch_orders = Order.query.filter_by(branchid=branch.id).count()
                branch_stats.append({
                    'branch': branch,
                    'products': branch_products,
                    'orders': branch_orders
                })
            except Exception as e:
                print(f"Error getting stats for branch {branch.id}: {e}")
                branch_stats.append({
                    'branch': branch,
                    'products': 0,
                    'orders': 0
                })
    except Exception as e:
        print(f"Error getting branch statistics: {e}")
        branch_stats = []
    
    # Top selling products (using completed payments to match sales report)
    try:
        top_products = db.session.query(
            BranchProduct, func.sum(OrderItem.quantity).label('total_sold'), func.avg(OrderItem.final_price).label('avg_final_price')
        ).join(OrderItem, BranchProduct.id == OrderItem.branch_productid).join(
            Order, OrderItem.orderid == Order.id
        ).join(
            Payment, Order.id == Payment.orderid
        ).filter(
            Payment.payment_status == 'completed'
        ).group_by(BranchProduct.id).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(5).all()
    except Exception as e:
        print(f"Error getting top products: {e}")
        top_products = []
    
    # Top products by asset value (buying price * stock)
    try:
        top_products_by_asset_value = db.session.query(
            BranchProduct, (BranchProduct.buyingprice * BranchProduct.stock).label('asset_value')
        ).filter(
            and_(
                BranchProduct.buyingprice.isnot(None),
                BranchProduct.buyingprice > 0,
                BranchProduct.stock.isnot(None),
                BranchProduct.stock > 0
            )
        ).order_by((BranchProduct.buyingprice * BranchProduct.stock).desc()).limit(5).all()
    except Exception as e:
        print(f"Error getting top products by asset value: {e}")
        top_products_by_asset_value = []
    
    # Calculate percentage of total assets for each top product
    top_products_with_percentage = []
    for product, asset_value in top_products_by_asset_value:
        percentage = (asset_value / total_product_asset * 100) if total_product_asset > 0 else 0
        top_products_with_percentage.append({
            'product': product,
            'asset_value': asset_value,
            'percentage': percentage
        })
    
    # Expense statistics
    try:
        total_expenses = Expense.query.count()
        pending_expenses = Expense.query.filter_by(status='pending').count()
        approved_expenses = Expense.query.filter_by(status='approved').count()
        total_expense_amount = db.session.query(func.sum(Expense.amount)).filter_by(status='approved').scalar() or 0
        monthly_expenses = db.session.query(func.sum(Expense.amount)).filter(
            and_(Expense.status == 'approved', Expense.expense_date >= this_month)
        ).scalar() or 0
    except Exception as e:
        print(f"Error getting expense statistics: {e}")
        total_expenses = 0
        pending_expenses = 0
        approved_expenses = 0
        total_expense_amount = 0
        monthly_expenses = 0
    
    try:
        return render_template("index.html", 
                             total_users=total_users,
                             total_products=total_products,
                             total_orders=total_orders,
                             total_branches=total_branches,
                             recent_orders=recent_orders,
                             pending_orders=pending_orders,
                             total_revenue=total_revenue,
                             monthly_revenue=monthly_revenue,
                             total_profit=total_profit,
                             monthly_profit=monthly_profit,
                             total_cogs=total_cogs,
                             monthly_cogs=monthly_cogs,
                             low_stock_products=low_stock_products,
                             recent_orders_list=recent_orders_list,
                             recent_users=recent_users,
                             branch_stats=branch_stats,
                             top_products=top_products,
                             top_products_by_asset_value=top_products_by_asset_value,
                             top_products_with_percentage=top_products_with_percentage,
                             total_expenses=total_expenses,
                             pending_expenses=pending_expenses,
                             approved_expenses=approved_expenses,
                             total_expense_amount=total_expense_amount,
                             monthly_expenses=monthly_expenses,
                             total_product_asset=total_product_asset,
                             products_with_assets=products_with_assets,
                             products_without_buying_price=products_without_buying_price,
                             products_with_zero_stock=products_with_zero_stock,
                             avg_asset_per_product=avg_asset_per_product)
    except Exception as e:
        print(f"Error in index route: {e}")
        flash('An error occurred while loading dashboard data. Please try again.', 'error')
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    print(f"🔍 Login route accessed - User authenticated: {current_user.is_authenticated}")
    if current_user.is_authenticated:
        print(f"🔍 User already authenticated, redirecting to index")
        return redirect(url_for('index'))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        if not email or not password:
            flash('Please provide both email and password.', 'danger')
            return render_template("login.html")
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template("login.html")
    
    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Temporarily allow registration without authentication
    # if current_user.is_authenticated:
    #     return redirect(url_for('index'))
        
    if request.method == "POST":
        email = request.form.get("email")
        firstname = request.form.get("firstname")
        lastname = request.form.get("lastname")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        phone = request.form.get("phone")
        
        # Validation
        if not email or not firstname or not lastname or not password or not confirm_password:
            flash('All required fields must be filled', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'danger')
            return redirect(url_for('register'))
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists. Please use a different email.', 'danger')
            return redirect(url_for('register'))
        
        # Get role from form
        role = request.form.get("role", "admin")
        
        # Create new user with hashed password
        new_user = User(
            email=email,
            firstname=firstname,
            lastname=lastname,
            password='',  # Will be set securely below
            role=role,
            phone=phone
        )
        new_user.set_password(password)  # Hash the password securely
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Admin user registered successfully! You can now login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(f"Error registering user: {e}")
            flash('An error occurred while registering. Please try again.', 'danger')
            return redirect(url_for('register'))
    
    return render_template("register.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/test_auth')
@login_required
def test_auth():
    return jsonify({
        'authenticated': current_user.is_authenticated,
        'user_id': current_user.id if current_user.is_authenticated else None,
        'email': current_user.email if current_user.is_authenticated else None,
        'role': current_user.role if current_user.is_authenticated else None
    })

@app.route('/debug_order/<int:order_id>')
@login_required
@role_required(['admin'])
def debug_order(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        debug_data = {
            'order_id': order.id,
            'order_number': order.ordernumber,
            'total_items': len(order.order_items),
            'items': []
        }
        
        for item in order.order_items:
            item_data = {
                'item_id': item.id,
                'product_id': item.productid,
                'product_name': item.product_name if hasattr(item, 'product_name') else None,
                'final_price': float(item.final_price) if item.final_price else None,
                'quantity': item.quantity,
                'has_product': item.branch_product is not None,
                'product_buying_price': float(item.branch_product.buyingprice) if item.branch_product and item.branch_product.buyingprice else None,
                'product_selling_price': float(item.branch_product.sellingprice) if item.branch_product and item.branch_product.sellingprice else None,
                'has_buying_price': hasattr(item, 'buying_price') and item.buying_price is not None,
                'buying_price': float(item.buying_price) if hasattr(item, 'buying_price') and item.buying_price else None,
                'has_original_price': hasattr(item, 'original_price') and item.original_price is not None,
                'original_price': float(item.original_price) if hasattr(item, 'original_price') and item.original_price else None
            }
            debug_data['items'].append(item_data)
        
        return jsonify(debug_data)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/unauthorized')
@login_required
def unauthorized():
    return render_template('unauthorized.html')

# Example of a protected route
@app.route("/dashboard")
@login_required
@role_required(['admin'])  # Only admin and manager can access
def dashboard():
    return render_template("dashboard.html")

# Configuration for file uploads (keeping for fallback)
UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
ALLOWED_EXTENSIONS = app.config['ALLOWED_EXTENSIONS']

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file):
    """Upload file to Cloudinary and return the URL"""
    try:
        # Upload the file to Cloudinary
        result = cloudinary.uploader.upload(
            file,
            folder="abz_products",  # Organize images in a folder
            resource_type="auto",
            transformation=[
                {'width': 800, 'height': 800, 'crop': 'limit'},  # Resize large images
                {'quality': 'auto:good'}  # Optimize quality
            ]
        )
        return result['secure_url']  # Return the secure HTTPS URL
    except Exception as e:
        print(f"Error uploading to Cloudinary: {e}")
        return None

def delete_from_cloudinary(public_id):
    """Delete image from Cloudinary using public_id"""
    try:
        if public_id:
            # Extract public_id from URL if full URL is provided
            if public_id.startswith('http'):
                # Extract public_id from Cloudinary URL
                parts = public_id.split('/')
                if 'abz_products' in parts:
                    idx = parts.index('abz_products')
                    public_id = '/'.join(parts[idx:]).split('.')[0]
            
            cloudinary.uploader.destroy(public_id)
            return True
    except Exception as e:
        print(f"Error deleting from Cloudinary: {e}")
        return False

# Custom template filter for formatting quantities
@app.template_filter('format_quantity')
def format_quantity(value):
    """Format quantity to remove unnecessary decimal places"""
    if value is None:
        return '0'
    
    try:
        # Convert to float first to handle both int and decimal types
        float_val = float(value)
        
        # If it's a whole number, display without decimals
        if float_val == int(float_val):
            return str(int(float_val))
        else:
            # If it has decimals, display with appropriate precision
            return f"{float_val:g}"  # 'g' format removes trailing zeros
    except (ValueError, TypeError):
        return str(value)

# Context processor to make branches available to all templates
@app.context_processor
def inject_branches():
    branches = Branch.query.order_by(Branch.name).all()
    return dict(branches=branches)

# Context processor to make user data available to all templates
@app.context_processor
def inject_user_data():
    if current_user.is_authenticated:
        return dict(
            current_user=current_user,
            user_full_name=f"{current_user.firstname} {current_user.lastname}",
            user_role=current_user.role.title()
        )
    return dict(current_user=None, user_full_name="", user_role="")

# Categories Routes
@app.route('/products')
@login_required
@role_required(['admin'])
def products():
    categories = Category.query.order_by(Category.name).all()
    subcategories = SubCategory.query.order_by(SubCategory.name).all()
    branches = Branch.query.order_by(Branch.name).all()
    
    # Get selected branch from query parameter - default to first branch if none selected
    selected_branch_id = request.args.get('branch_id', type=int)
    if not selected_branch_id and branches:
        selected_branch_id = branches[0].id
    
    # Search and filter parameters
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    display_filter = request.args.get('display', '')
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)  # Default 10 items per page
    
    # Base query - show BranchProduct items for the selected branch
    base_query = BranchProduct.query.join(
        ProductCatalog, BranchProduct.catalog_id == ProductCatalog.id
    ).join(
        SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
    ).join(
        Category, SubCategory.category_id == Category.id, isouter=True
    ).join(
        Branch, BranchProduct.branchid == Branch.id
    )
    
    # Apply filters
    if selected_branch_id:
        base_query = base_query.filter(BranchProduct.branchid == selected_branch_id)
    
    if search:
        base_query = base_query.filter(
            or_(
                ProductCatalog.name.ilike(f'%{search}%'),
                ProductCatalog.productcode.ilike(f'%{search}%'),
                SubCategory.name.ilike(f'%{search}%'),
                Category.name.ilike(f'%{search}%')
            )
        )
    
    if category_filter:
        base_query = base_query.filter(SubCategory.name == category_filter)
    
    if display_filter:
        if display_filter == 'active':
            base_query = base_query.filter(BranchProduct.display == True)
        elif display_filter == 'inactive':
            base_query = base_query.filter(BranchProduct.display == False)
    
    # Apply pagination
    pagination = base_query.order_by(BranchProduct.id).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    products = pagination.items
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return only the table content for AJAX requests
        return render_template('products_table_partial.html', 
                             products=products, 
                             branches=branches,
                             selected_branch_id=selected_branch_id,
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter,
                             display_filter=display_filter)
    else:
        # Return full page for regular requests
        return render_template('products.html', 
                             categories=categories, 
                             subcategories=subcategories,
                             products=products, 
                             branches=branches,
                             selected_branch_id=selected_branch_id,
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter,
                             display_filter=display_filter)

@app.route('/export_products_csv')
@login_required
@role_required(['admin'])
def export_products_csv():
    try:
        # Get branch filter from query parameter
        branch_id = request.args.get('branch_id', type=int)
        
        # Base query with joins
        base_query = ProductCatalog.query.join(
            SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
        ).join(
            Category, SubCategory.category_id == Category.id, isouter=True
        )
        
        # Note: ProductCatalog is global, so we don't filter by branch_id
        
        # Get all catalog products
        products = base_query.all()
        
        # Create CSV data
        csv_data = []
        csv_data.append([
            'ProductCatalog ID', 'ProductCatalog Code', 'ProductCatalog Name', 'Category', 'Subcategory', 
            'Image URL'
        ])
        
        for product in products:
            # Get category and subcategory names
            category_name = ''
            subcategory_name = ''
            if hasattr(product, 'sub_category') and product.sub_category:
                subcategory_name = product.sub_category.name
                if product.sub_category.category:
                    category_name = product.sub_category.category.name
            elif product.subcategory_id:
                # Fallback: query directly
                subcategory = SubCategory.query.get(product.subcategory_id)
                if subcategory:
                    subcategory_name = subcategory.name
                    if subcategory.category:
                        category_name = subcategory.category.name
            
            csv_data.append([
                product.id,
                product.productcode or '',
                product.name or '',
                category_name,
                subcategory_name,
                product.image_url or ''
            ])
        
        # Create CSV response
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=products_export.csv'
        
        return response
        
    except Exception as e:
        print(f"Error exporting products to CSV: {e}")
        flash('An error occurred while exporting products.', 'error')
        return redirect(url_for('products'))

@app.route('/export_products_by_category_csv')
@login_required
@role_required(['admin'])
def export_products_by_category_csv():
    try:
        # Get branch filter from query parameter
        branch_id = request.args.get('branch_id', type=int)
        
        if branch_id:
            # Export branch-specific products
            base_query = BranchProduct.query.filter(BranchProduct.branchid == branch_id).join(
                ProductCatalog, BranchProduct.catalog_id == ProductCatalog.id
            ).join(
                SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
            ).join(
                Category, SubCategory.category_id == Category.id, isouter=True
            )
            
            # Get all branch products ordered by category
            branch_products = base_query.order_by(Category.name, ProductCatalog.name).all()
            
            # Group products by category
            products_by_category = {}
            for branch_product in branch_products:
                product = branch_product.catalog_product
                # Get category name through the join
                category_name = 'Uncategorized'
                if hasattr(product, 'sub_category') and product.sub_category and product.sub_category.category:
                    category_name = product.sub_category.category.name
                elif product.subcategory_id:
                    # Fallback: query the subcategory and category directly
                    subcategory = SubCategory.query.get(product.subcategory_id)
                    if subcategory and subcategory.category:
                        category_name = subcategory.category.name
                
                if category_name not in products_by_category:
                    products_by_category[category_name] = []
                products_by_category[category_name].append({
                    'product': product,
                    'branch_product': branch_product
                })
            
            # Create CSV data with branch-specific information
            csv_data = []
            csv_data.append(['Category', 'Product Name', 'Product Code', 'Buying Price', 'Selling Price', 'Stock'])
            
            # Add products grouped by category
            for category_name in sorted(products_by_category.keys()):
                category_products = products_by_category[category_name]
                for i, item in enumerate(category_products):
                    product = item['product']
                    branch_product = item['branch_product']
                    
                    # Use only product name
                    product_name = product.name or ''
                    
                    if i == 0:
                        # First product in category - include category name
                        csv_data.append([
                            category_name,
                            product_name,
                            product.productcode or '',
                            branch_product.buyingprice or '',
                            branch_product.sellingprice or '',
                            branch_product.stock or ''
                        ])
                    else:
                        # Subsequent products in category - leave category name empty
                        csv_data.append([
                            '',  # Empty category name for grouping
                            product_name,
                            product.productcode or '',
                            branch_product.buyingprice or '',
                            branch_product.sellingprice or '',
                            branch_product.stock or ''
                        ])
            
            # Get branch name for filename
            branch = Branch.query.get(branch_id)
            branch_name = branch.name.lower().replace(' ', '_') if branch else 'branch'
            filename = f"products_by_category_{branch_name}.csv"
            
        else:
            # Export global catalog products (original behavior)
            base_query = ProductCatalog.query.join(
                SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
            ).join(
                Category, SubCategory.category_id == Category.id, isouter=True
            )
            
            # Get all catalog products ordered by category
            products = base_query.order_by(Category.name, ProductCatalog.name).all()
            
            # Group products by category
            products_by_category = {}
            for product in products:
                # Get category name through the join
                category_name = 'Uncategorized'
                if hasattr(product, 'sub_category') and product.sub_category and product.sub_category.category:
                    category_name = product.sub_category.category.name
                elif product.subcategory_id:
                    # Fallback: query the subcategory and category directly
                    subcategory = SubCategory.query.get(product.subcategory_id)
                    if subcategory and subcategory.category:
                        category_name = subcategory.category.name
                
                if category_name not in products_by_category:
                    products_by_category[category_name] = []
                products_by_category[category_name].append(product)
            
            # Create CSV data
            csv_data = []
            csv_data.append(['Category', 'Product Name', 'Product Code'])
            
            # Add products grouped by category
            for category_name in sorted(products_by_category.keys()):
                category_products = products_by_category[category_name]
                for i, product in enumerate(category_products):
                    # Use only product name
                    product_name = product.name or ''
                    
                    if i == 0:
                        # First product in category - include category name
                        csv_data.append([
                            category_name,
                            product_name,
                            product.productcode or ''
                        ])
                    else:
                        # Subsequent products in category - leave category name empty
                        csv_data.append([
                            '',  # Empty category name for grouping
                            product_name,
                            product.productcode or ''
                        ])
            
            filename = "products_by_category_all_branches.csv"
        
        # Create CSV response
        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"Error exporting products by category to CSV: {e}")
        flash('An error occurred while exporting products by category.', 'error')
        return redirect(url_for('products'))

@app.route('/export_products_by_category_pdf')
@login_required
@role_required(['admin'])
def export_products_by_category_pdf():
    try:
        # Get branch filter from query parameter
        branch_id = request.args.get('branch_id', type=int)
        branch = None
        if branch_id:
            branch = Branch.query.get(branch_id)
        
        if branch_id:
            # Export branch-specific products
            base_query = BranchProduct.query.filter(BranchProduct.branchid == branch_id).join(
                ProductCatalog, BranchProduct.catalog_id == ProductCatalog.id
            ).join(
                SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
            ).join(
                Category, SubCategory.category_id == Category.id, isouter=True
            )
            
            # Get all branch products ordered by category
            branch_products = base_query.order_by(Category.name, ProductCatalog.name).all()
            
            # Group products by category
            products_by_category = {}
            for branch_product in branch_products:
                product = branch_product.catalog_product
                # Get category name through the join
                category_name = 'Uncategorized'
                if hasattr(product, 'sub_category') and product.sub_category and product.sub_category.category:
                    category_name = product.sub_category.category.name
                elif product.subcategory_id:
                    # Fallback: query the subcategory and category directly
                    subcategory = SubCategory.query.get(product.subcategory_id)
                    if subcategory and subcategory.category:
                        category_name = subcategory.category.name
                
                if category_name not in products_by_category:
                    products_by_category[category_name] = []
                products_by_category[category_name].append({
                    'product': product,
                    'branch_product': branch_product
                })
        else:
            # Export global catalog products (original behavior)
            base_query = ProductCatalog.query.join(
                SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
            ).join(
                Category, SubCategory.category_id == Category.id, isouter=True
            )
            
            # Get all catalog products ordered by category
            products = base_query.order_by(Category.name, ProductCatalog.name).all()
            
            # Group products by category
            products_by_category = {}
            for product in products:
                # Get category name through the join
                category_name = 'Uncategorized'
                if hasattr(product, 'sub_category') and product.sub_category and product.sub_category.category:
                    category_name = product.sub_category.category.name
                elif product.subcategory_id:
                    # Fallback: query the subcategory and category directly
                    subcategory = SubCategory.query.get(product.subcategory_id)
                    if subcategory and subcategory.category:
                        category_name = subcategory.category.name
                
                if category_name not in products_by_category:
                    products_by_category[category_name] = []
                products_by_category[category_name].append({
                    'product': product,
                    'branch_product': None
                })
        
        # Create PDF buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#2c3e50')
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            textColor=colors.HexColor('#34495e')
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=12
        )
        
        # Load the logo image
        try:
            logo_path = os.path.join(app.static_folder, 'assets', 'img', 'logo.png')
            print(f"Loading logo from: {logo_path}")
            logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
            logo_cell = logo_image
        except Exception as e:
            print(f"Error loading logo: {e}")
            # Create a placeholder if logo fails to load
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=18 color="#1a365d">ABZ HARDWARE LIMITED</font></b>
            </para>
            ''', normal_style)
        
        # Create the letterhead table for proper layout
        letterhead_data = [
            [logo_cell, Paragraph('''
            <para align=right>
            <b><font size=18 color="#1a365d">ABZ HARDWARE LIMITED</font></b><br/>
            <font size=12 color="#4a5568">Your Trusted Hardware Partner</font>
            </para>
            ''', normal_style)]
        ]
        
        letterhead_table = Table(letterhead_data, colWidths=[2*inch, 4*inch])
        letterhead_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        elements.append(letterhead_table)
        elements.append(Spacer(1, 20))
        
        # Title
        elements.append(Paragraph("PRODUCTS BY CATEGORY", title_style))
        elements.append(Spacer(1, 30))
        
        # Branch information
        if branch:
            branch_info = f"""
            <b>Branch:</b> {branch.name}<br/>
            <b>Location:</b> {branch.location}<br/>
            <b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"""
        else:
            branch_info = f"""
            <b>All Branches</b><br/>
            <b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"""
        
        elements.append(Paragraph(branch_info, normal_style))
        elements.append(Spacer(1, 30))
        
        # Products by category
        for category_name in sorted(products_by_category.keys()):
            category_products = products_by_category[category_name]
            
            # Category header
            elements.append(Paragraph(f"<b>{category_name.upper()}</b>", heading_style))
            
            # Create table for products in this category
            if branch_id:
                # Branch-specific export - include pricing and stock info
                table_data = [['Product Name', 'Product Code', 'Buying Price', 'Selling Price', 'Stock']]
                col_widths = [2.8*inch, 1.2*inch, 1*inch, 1*inch, 0.8*inch]
                
                for item in category_products:
                    product = item['product']
                    branch_product = item['branch_product']
                    product_name = product.name or 'N/A'
                    product_code = product.productcode or 'N/A'
                    buying_price = f"KSh {branch_product.buyingprice}" if branch_product.buyingprice else 'N/A'
                    selling_price = f"KSh {branch_product.sellingprice}" if branch_product.sellingprice else 'N/A'
                    stock = str(branch_product.stock) if branch_product.stock is not None else 'N/A'
                    table_data.append([product_name, product_code, buying_price, selling_price, stock])
            else:
                # Global catalog export - basic info only
                table_data = [['Product Name', 'Product Code']]
                col_widths = [4*inch, 2*inch]
                
                for item in category_products:
                    product = item['product']
                    product_name = product.name or 'N/A'
                    product_code = product.productcode or 'N/A'
                    table_data.append([product_name, product_code])
            
            # Create table
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10 if branch_id else 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                
                # Data styling
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Product name left
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),  # Other columns center
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9 if branch_id else 10),
                ('TOPPADDING', (0, 1), (-1, -1), 6 if branch_id else 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6 if branch_id else 8),
                ('LEFTPADDING', (0, 1), (-1, -1), 6 if branch_id else 8),
                ('RIGHTPADDING', (0, 1), (-1, -1), 6 if branch_id else 8),
                
                # Grid
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Create response
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        filename = f"products_by_category_{branch.name.lower().replace(' ', '_') if branch else 'all_branches'}.pdf"
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"Error exporting products by category to PDF: {e}")
        flash('An error occurred while exporting products by category to PDF.', 'error')
        return redirect(url_for('products'))

@app.route('/branch_products/<int:branch_id>')
@login_required
@role_required(['admin'])
def branch_products(branch_id):
    # Get the specific branch
    branch = Branch.query.get_or_404(branch_id)
    categories = Category.query.order_by(Category.name).all()
    subcategories = SubCategory.query.order_by(SubCategory.name).all()
    branches = Branch.query.order_by(Branch.name).all()
    
    # Search and filter parameters
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    display_filter = request.args.get('display', '')
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Filter branch products by the specific branch and join with catalog and categories for search
    base_query = BranchProduct.query.filter(BranchProduct.branchid == branch_id).join(
        ProductCatalog, BranchProduct.catalog_id == ProductCatalog.id
    ).join(
        SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
    ).join(
        Category, SubCategory.category_id == Category.id, isouter=True
    )
    
    # Apply search filters
    if search:
        base_query = base_query.filter(
            or_(
                ProductCatalog.name.ilike(f'%{search}%'),
                ProductCatalog.productcode.ilike(f'%{search}%'),
                SubCategory.name.ilike(f'%{search}%'),
                Category.name.ilike(f'%{search}%')
            )
        )
    
    if category_filter:
        base_query = base_query.filter(SubCategory.name == category_filter)
    
    if display_filter == 'true':
        base_query = base_query.filter(BranchProduct.display == True)
    elif display_filter == 'false':
        base_query = base_query.filter(BranchProduct.display == False)
    
    # Apply pagination
    pagination = base_query.order_by(BranchProduct.id).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    branch_products = pagination.items
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return only the table content for AJAX requests
        return render_template('branch_products_table_partial.html', 
                             branch=branch,
                             branch_products=branch_products, 
                             branches=branches,
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter,
                             display_filter=display_filter)
    else:
        # Return full page for regular requests
        return render_template('branch_products.html', 
                             branch=branch,
                             categories=categories, 
                             subcategories=subcategories,
                             branch_products=branch_products, 
                             branches=branches,
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter,
                             display_filter=display_filter)

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_category():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Category name is required', 'error')
            return redirect(url_for('add_category'))
        
        # Check if category name already exists
        existing_category = Category.query.filter_by(name=name).first()
        if existing_category:
            flash('Category name already exists. Please use a different name.', 'error')
            return redirect(url_for('add_category'))
        
        # Handle image upload to Cloudinary
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                try:
                    # Upload to Cloudinary
                    image_url = upload_to_cloudinary(file)
                    if not image_url:
                        flash('Failed to upload image. Please try again.', 'error')
                        return redirect(url_for('add_category'))
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
                    return redirect(url_for('add_category'))
        
        new_category = Category(name=name, description=description, image_url=image_url)
        db.session.add(new_category)
        db.session.commit()
        
        flash('Category added successfully', 'success')
        return redirect(url_for('categories'))
    
    return render_template('add_category.html')

@app.route('/edit_category/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_category(id):
    category = Category.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        if not name:
            flash('Category name is required', 'error')
            return redirect(url_for('edit_category', id=id))
        # Check if category name already exists (excluding current category)
        existing_category = Category.query.filter_by(name=name).first()
        if existing_category and existing_category.id != id:
            flash('Category name already exists. Please use a different name.', 'error')
            return redirect(url_for('edit_category', id=id))
        
        # Handle image upload if a new image is provided
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                try:
                    # Delete old image from Cloudinary if it exists
                    if category.image_url:
                        delete_from_cloudinary(category.image_url)
                    
                    # Upload new image to Cloudinary
                    image_url = upload_to_cloudinary(file)
                    if not image_url:
                        flash('Failed to upload new image. Please try again.', 'error')
                        return redirect(url_for('edit_category', id=id))
                    
                    category.image_url = image_url
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
                    return redirect(url_for('edit_category', id=id))
        
        category.name = name
        category.description = description
        db.session.commit()
        flash('Category updated successfully', 'success')
        return redirect(url_for('categories'))
    return render_template('edit_category.html', category=category)

@app.route('/delete_category/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_category(id):
    try:
        category = Category.query.get_or_404(id)
        if category.products:
            flash('Cannot delete category with associated products', 'error')
            return redirect(url_for('categories'))
        db.session.delete(category)
        db.session.commit()
        flash('Category deleted successfully', 'success')
        return redirect(url_for('categories'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this category. It has associated products or other related records.', 'error')
        return redirect(url_for('categories'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the category. Please try again.', 'error')
        return redirect(url_for('categories'))

# ProductCatalog Catalog Routes
@app.route('/product_catalog')
@login_required
@role_required(['admin'])
def product_catalog():
    categories = Category.query.order_by(Category.name).all()
    subcategories = SubCategory.query.order_by(SubCategory.name).all()
    
    # Search and filter parameters
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Base query - join with SubCategory and Category for better search
    base_query = ProductCatalog.query.join(
        SubCategory, ProductCatalog.subcategory_id == SubCategory.id, isouter=True
    ).join(
        Category, SubCategory.category_id == Category.id, isouter=True
    )
    
    # Apply filters
    if search:
        base_query = base_query.filter(
            or_(
                ProductCatalog.name.ilike(f'%{search}%'),
                ProductCatalog.productcode.ilike(f'%{search}%'),
                SubCategory.name.ilike(f'%{search}%'),
                Category.name.ilike(f'%{search}%')
            )
        )
    
    if category_filter:
        base_query = base_query.filter(SubCategory.name == category_filter)
    
    # Apply pagination
    pagination = base_query.order_by(ProductCatalog.id).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    catalog_products = pagination.items
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return only the table content for AJAX requests
        return render_template('product_catalog_table_partial.html', 
                             categories=categories,
                             subcategories=subcategories,
                             catalog_products=catalog_products, 
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter)
    else:
        # Return full page for regular requests
        return render_template('product_catalog.html', 
                             categories=categories, 
                             subcategories=subcategories,
                             catalog_products=catalog_products, 
                             pagination=pagination,
                             search=search,
                             category_filter=category_filter)

@app.route('/add_product_to_catalog', methods=['POST'])
@login_required
@role_required(['admin'])
def add_product_to_catalog():
    # Get form data
    name = request.form.get('name')
    subcategory_id = request.form.get('subcategory_id')
    productcode = request.form.get('productcode')
    
    # Basic validation
    if not name:
        flash('ProductCatalog name is required', 'error')
        return redirect(url_for('product_catalog'))
    
    # Handle file upload to Cloudinary
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            try:
                # Upload to Cloudinary
                image_url = upload_to_cloudinary(file)
                if not image_url:
                    flash('Failed to upload image. Please try again.', 'error')
                    return redirect(url_for('product_catalog'))
            except Exception as e:
                flash(f'Error uploading image: {str(e)}', 'error')
                return redirect(url_for('product_catalog'))
    
    # Convert empty strings to None
    subcategory_id = int(subcategory_id) if subcategory_id else None
    
    new_catalog_product = ProductCatalog(
        name=name,
        subcategory_id=subcategory_id,
        productcode=productcode,
        image_url=image_url
    )
    
    db.session.add(new_catalog_product)
    db.session.commit()
    
    flash('ProductCatalog added to catalog successfully', 'success')
    return redirect(url_for('product_catalog'))

@app.route('/edit_catalog_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_catalog_product(id):
    catalog_product = ProductCatalog.query.get_or_404(id)
    
    # Get form data
    catalog_product.name = request.form.get('name')
    catalog_product.subcategory_id = request.form.get('subcategory_id') if request.form.get('subcategory_id') else None
    catalog_product.productcode = request.form.get('productcode')
    
    # Basic validation
    if not catalog_product.name:
        flash('ProductCatalog name is required', 'error')
        return redirect(url_for('product_catalog'))
    
    # Handle file upload if a new image is provided
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            try:
                # Delete old image from Cloudinary if it exists
                if catalog_product.image_url:
                    delete_from_cloudinary(catalog_product.image_url)
                
                # Upload new image to Cloudinary
                image_url = upload_to_cloudinary(file)
                if not image_url:
                    flash('Failed to upload new image. Please try again.', 'error')
                    return redirect(url_for('product_catalog'))
                
                catalog_product.image_url = image_url
            except Exception as e:
                flash(f'Error uploading image: {str(e)}', 'error')
                return redirect(url_for('product_catalog'))
    
    db.session.commit()
    
    flash('Catalog product updated successfully', 'success')
    return redirect(url_for('product_catalog'))

@app.route('/delete_catalog_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_catalog_product(id):
    try:
        catalog_product = ProductCatalog.query.get_or_404(id)
        
        # Check if catalog product has branch products
        if catalog_product.branch_products:
            flash('Cannot delete this catalog product. It has associated branch products.', 'error')
            return redirect(url_for('product_catalog'))
        
        # Delete associated image if exists
        if catalog_product.image_url:
            try:
                delete_from_cloudinary(catalog_product.image_url)
            except Exception as e:
                print(f"Error deleting image from Cloudinary: {e}")
        
        db.session.delete(catalog_product)
        db.session.commit()
        
        flash('Catalog product deleted successfully', 'success')
        return redirect(url_for('product_catalog'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this catalog product. It has associated branch products or other related records.', 'error')
        return redirect(url_for('product_catalog'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the catalog product. Please try again.', 'error')
        return redirect(url_for('product_catalog'))

@app.route('/get_catalog_product/<int:id>')
@login_required
@role_required(['admin'])
def get_catalog_product(id):
    catalog_product = ProductCatalog.query.get_or_404(id)
    return jsonify({
        'id': catalog_product.id,
        'name': catalog_product.name,
        'productcode': catalog_product.productcode,
        'subcategory_id': catalog_product.subcategory_id,
        'image_url': catalog_product.image_url
    })

# Branch ProductCatalogs Routes
@app.route('/add_branch_product', methods=['POST'])
@login_required
@role_required(['admin'])
def add_branch_product():
    # Get form data
    catalog_id = request.form.get('catalog_id')
    branchid = request.form.get('branchid')
    buyingprice = request.form.get('buyingprice')
    sellingprice = request.form.get('sellingprice')
    stock = request.form.get('stock')
    display = request.form.get('display') == 'on'
    
    # Basic validation
    if not catalog_id or not branchid:
        flash('Catalog product and Branch are required', 'error')
        return redirect(url_for('products', branch_id=branchid))
    
    # Check if branch product already exists for this catalog product and branch
    existing_branch_product = BranchProduct.query.filter_by(
        catalog_id=catalog_id, 
        branchid=branchid
    ).first()
    
    if existing_branch_product:
        flash('This product already exists in this branch. Please edit the existing entry instead.', 'error')
        return redirect(url_for('products', branch_id=branchid))
    
    # Convert empty strings to None
    buyingprice = float(buyingprice) if buyingprice else None
    sellingprice = float(sellingprice) if sellingprice else None
    
    # Handle stock conversion properly - convert decimal to int
    if stock:
        try:
            # Convert to float first to handle decimals, then to int
            stock = int(float(stock))
        except (ValueError, TypeError):
            stock = None
    else:
        stock = None
    
    new_branch_product = BranchProduct(
        catalog_id=catalog_id,
        branchid=branchid,
        buyingprice=buyingprice,
        sellingprice=sellingprice,
        stock=stock,
        display=display
    )
    
    db.session.add(new_branch_product)
    db.session.commit()
    
    flash('ProductCatalog added to branch successfully', 'success')
    return redirect(url_for('branch_products', branch_id=branchid))

@app.route('/edit_branch_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_branch_product(id):
    branch_product = BranchProduct.query.get_or_404(id)
    
    # Get form data
    branch_product.buyingprice = float(request.form.get('buyingprice')) if request.form.get('buyingprice') else None
    branch_product.sellingprice = float(request.form.get('sellingprice')) if request.form.get('sellingprice') else None
    
    # Handle stock conversion properly - convert decimal to int
    stock_value = request.form.get('stock')
    if stock_value:
        try:
            # Convert to float first to handle decimals, then to int
            branch_product.stock = int(float(stock_value))
        except (ValueError, TypeError):
            branch_product.stock = None
    else:
        branch_product.stock = None
    
    branch_product.display = request.form.get('display') == 'on'
    
    db.session.commit()
    
    flash('Branch product updated successfully', 'success')
    return redirect(url_for('products', branch_id=branch_product.branchid))

@app.route('/delete_branch_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_branch_product(id):
    try:
        branch_product = BranchProduct.query.get_or_404(id)
        branch_id = branch_product.branchid
        
        # Check if branch product has related records
        if branch_product.order_items or branch_product.stock_transactions:
            flash('Cannot delete this branch product. It has associated orders or stock transactions.', 'error')
            return redirect(url_for('products', branch_id=branch_id))
        
        db.session.delete(branch_product)
        db.session.commit()
        
        flash('Branch product deleted successfully', 'success')
        return redirect(url_for('products', branch_id=branch_id))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this branch product. It has associated orders, stock transactions, or other related records.', 'error')
        return redirect(url_for('products', branch_id=branch_id))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the branch product. Please try again.', 'error')
        return redirect(url_for('products', branch_id=branch_id))

@app.route('/get_branch_product/<int:id>')
@login_required
@role_required(['admin'])
def get_branch_product(id):
    branch_product = BranchProduct.query.get_or_404(id)
    return jsonify({
        'id': branch_product.id,
        'catalog_id': branch_product.catalog_id,
        'branchid': branch_product.branchid,
        'buyingprice': branch_product.buyingprice,
        'sellingprice': branch_product.sellingprice,
        'stock': branch_product.stock,
        'display': branch_product.display,
        'catalog_product_name': branch_product.catalog_product.name if branch_product.catalog_product else None
    })

@app.route('/get_catalog_products_for_branch')
@login_required
@role_required(['admin'])
def get_catalog_products_for_branch():
    branch_id = request.args.get('branch_id', type=int)
    search = request.args.get('search', '')
    
    # Get catalog products that are not already in this branch
    existing_catalog_ids = db.session.query(BranchProduct.catalog_id).filter_by(branchid=branch_id).subquery()
    
    base_query = ProductCatalog.query.filter(~ProductCatalog.id.in_(existing_catalog_ids))
    
    if search:
        base_query = base_query.filter(
            or_(
                ProductCatalog.name.ilike(f'%{search}%'),
                ProductCatalog.productcode.ilike(f'%{search}%')
            )
        )
    
    catalog_products = base_query.limit(20).all()
    
    return jsonify([{
        'id': cp.id,
        'name': cp.name,
        'productcode': cp.productcode,
        'image_url': cp.image_url
    } for cp in catalog_products])

# ProductCatalogs Routes (Legacy - to be removed later)
# DEPRECATED: Legacy product route - use ProductCatalog instead
# @app.route('/add_product', methods=['POST'])
# @login_required
# @role_required(['admin'])
# def add_product():
    # Get form data
    name = request.form.get('name')
    subcategory_id = request.form.get('subcategory_id')
    branchid = request.form.get('branchid')  # Get branch ID from form
    buyingprice = request.form.get('buyingprice')
    sellingprice = request.form.get('sellingprice')
    stock = request.form.get('stock')
    productcode = request.form.get('productcode')
    
    # Basic validation
    if not name or not branchid:
        flash('Name and Branch are required', 'error')
        return redirect(url_for('products'))
    
    # Handle file upload to Cloudinary
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            try:
                # Upload to Cloudinary
                image_url = upload_to_cloudinary(file)
                if not image_url:
                    flash('Failed to upload image. Please try again.', 'error')
                    return redirect(url_for('products'))
            except Exception as e:
                flash(f'Error uploading image: {str(e)}', 'error')
                return redirect(url_for('products'))
    
    # Convert empty strings to None
    buyingprice = int(buyingprice) if buyingprice else None
    sellingprice = int(sellingprice) if sellingprice else None
    stock = int(stock) if stock else None
    
    # Handle display field
    display = request.form.get('display') == 'on'
    
    new_product = ProductCatalog(
        name=name,
        subcategory_id=subcategory_id if subcategory_id else None,
        branchid=branchid,  # Use the selected branch ID
        buyingprice=buyingprice,
        sellingprice=sellingprice,
        stock=stock,
        productcode=productcode,
        image_url=image_url,
        display=display
    )
    
    db.session.add(new_product)
    db.session.commit()
    
    flash('ProductCatalog added successfully', 'success')
    return redirect(url_for('products'))

# DEPRECATED: Legacy product route - use ProductCatalog instead
# @app.route('/get_product/<int:id>')
# @login_required
# @role_required(['admin'])
# def get_product(id):
#     product = ProductCatalog.query.get_or_404(id)
#     return jsonify({
#         'id': product.id,
#         'name': product.name,
#         'productcode': product.productcode,
#         'subcategory_id': product.subcategory_id,
#         'branchid': product.branchid,
#         'buyingprice': product.buyingprice,
#         'sellingprice': product.sellingprice,
#         'stock': product.stock,
#         'display': product.display,
#         'image_url': product.image_url
#     })

# DEPRECATED: Legacy product route - use ProductCatalog instead
# @app.route('/edit_product/<int:id>', methods=['POST'])
# @login_required
# @role_required(['admin'])
# def edit_product(id):
    product = ProductCatalog.query.get_or_404(id)
    
    # Get form data
    product.name = request.form.get('name')
    product.subcategory_id = request.form.get('subcategory_id') if request.form.get('subcategory_id') else None
    product.branchid = request.form.get('branchid')  # Get branch ID from form
    product.buyingprice = int(request.form.get('buyingprice')) if request.form.get('buyingprice') else None
    product.sellingprice = int(request.form.get('sellingprice')) if request.form.get('sellingprice') else None
    product.stock = int(request.form.get('stock')) if request.form.get('stock') else None
    product.productcode = request.form.get('productcode')
    
    # Handle display field
    product.display = request.form.get('display') == 'on'
    
    # Basic validation
    if not product.name or not product.branchid:
        flash('Name and Branch are required', 'error')
        return redirect(url_for('products'))
    
    # Handle file upload if a new image is provided
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            try:
                # Delete old image from Cloudinary if it exists
                if product.image_url:
                    delete_from_cloudinary(product.image_url)
                
                # Upload new image to Cloudinary
                image_url = upload_to_cloudinary(file)
                if not image_url:
                    flash('Failed to upload new image. Please try again.', 'error')
                    return redirect(url_for('products'))
                
                product.image_url = image_url
            except Exception as e:
                flash(f'Error uploading image: {str(e)}', 'error')
                return redirect(url_for('products'))
    
    db.session.commit()
    
    flash('ProductCatalog updated successfully', 'success')
    return redirect(url_for('products'))

@app.route('/delete_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_product(id):
    try:
        product = ProductCatalog.query.get_or_404(id)
        
        # Check if product has related records
        if product.order_items or product.stock_transactions:
            flash('Cannot delete this product. It has associated orders or stock transactions.', 'error')
            return redirect(url_for('products'))
        
        # Delete associated image if exists
        if product.image_url:
            try:
                delete_from_cloudinary(product.image_url)
            except Exception as e:
                print(f"Error deleting image from Cloudinary: {e}")
        
        db.session.delete(product)
        db.session.commit()
        
        flash('ProductCatalog deleted successfully', 'success')
        return redirect(url_for('products'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this product. It has associated orders, stock transactions, or other related records.', 'error')
        return redirect(url_for('products'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the product. Please try again.', 'error')
        return redirect(url_for('products'))

# Stock Management Routes
@app.route('/add_stock/<int:branch_product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def add_stock(branch_product_id):
    branch_product = BranchProduct.query.get_or_404(branch_product_id)
    
    # Get form data
    quantity = request.form.get('quantity')
    notes = request.form.get('notes', '')
    
    # Basic validation
    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash('Please enter a valid positive quantity', 'error')
        return redirect(url_for('products', branch_id=branch_product.branchid))
    
    quantity = int(quantity)
    previous_stock = branch_product.stock or 0
    new_stock = previous_stock + quantity
    
    # Update branch product stock
    branch_product.stock = new_stock
    
    # Create stock transaction record
    stock_transaction = StockTransaction(
        branch_productid=branch_product_id,
        userid=current_user.id,
        transaction_type='add',
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        notes=notes
    )
    
    db.session.add(stock_transaction)
    db.session.commit()
    
    product_name = branch_product.catalog_product.name if branch_product.catalog_product else 'Unknown ProductCatalog'
    flash(f'Successfully added {quantity} units to {product_name}. New stock: {new_stock}', 'success')
    return redirect(url_for('products', branch_id=branch_product.branchid))

@app.route('/remove_stock/<int:branch_product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def remove_stock(branch_product_id):
    branch_product = BranchProduct.query.get_or_404(branch_product_id)
    
    # Get form data
    quantity = request.form.get('quantity')
    notes = request.form.get('notes', '')
    
    # Basic validation
    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash('Please enter a valid positive quantity', 'error')
        return redirect(url_for('products', branch_id=branch_product.branchid))
    
    quantity = int(quantity)
    previous_stock = branch_product.stock or 0
    
    # Check if we have enough stock
    if previous_stock < quantity:
        flash(f'Insufficient stock. Current stock: {previous_stock}, trying to remove: {quantity}', 'error')
        return redirect(url_for('products', branch_id=branch_product.branchid))
    
    new_stock = previous_stock - quantity
    
    # Update branch product stock
    branch_product.stock = new_stock
    
    # Create stock transaction record
    stock_transaction = StockTransaction(
        branch_productid=branch_product_id,
        userid=current_user.id,
        transaction_type='remove',
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        notes=notes
    )
    
    db.session.add(stock_transaction)
    db.session.commit()
    
    product_name = branch_product.catalog_product.name if branch_product.catalog_product else 'Unknown ProductCatalog'
    flash(f'Successfully removed {quantity} units from {product_name}. New stock: {new_stock}', 'success')
    return redirect(url_for('products', branch_id=branch_product.branchid))

@app.route('/stock_history/<int:branch_product_id>')
@login_required
@role_required(['admin'])
def stock_history(branch_product_id):
    branch_product = BranchProduct.query.get_or_404(branch_product_id)
    transactions = StockTransaction.query.filter_by(branch_productid=branch_product_id).order_by(StockTransaction.created_at.desc()).all()
    
    # Add adjusted times (3 hours ahead) for display
    for transaction in transactions:
        transaction.created_at_adjusted = transaction.created_at + timedelta(hours=3)
    
    return render_template('stock_history.html', branch_product=branch_product, transactions=transactions)

@app.route('/toggle_display/<int:branch_product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def toggle_display(branch_product_id):
    try:
        branch_product = BranchProduct.query.get_or_404(branch_product_id)
        branch_product.display = not branch_product.display
        db.session.commit()
        
        status = "visible" if branch_product.display else "hidden"
        product_name = branch_product.catalog_product.name if branch_product.catalog_product else 'Unknown ProductCatalog'
        flash(f'ProductCatalog "{product_name}" is now {status} in customer app', 'success')
        return redirect(url_for('products', branch_id=branch_product.branchid))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating product display status', 'error')
        return redirect(url_for('products', branch_id=branch_product.branchid))

# User Management Routes
@app.route('/users')
@login_required
@role_required(['admin'])
def users():
    try:
        print("Users route accessed")
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get all users with pagination
        pagination = User.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        print(f"Pagination object: {pagination}")
        users = pagination.items
        print(f"Users found: {len(users)}")
        
        # Add adjusted times (3 hours ahead) for display
        for user in users:
            user.created_at_adjusted = user.created_at + timedelta(hours=3)
        
        return render_template('users.html', users=users, pagination=pagination)
    except Exception as e:
        print(f"Error in users route: {e}")
        db.session.rollback()
        flash('An error occurred while loading users. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_user():
    if request.method == 'POST':
        # Get form data
        email = request.form.get('email')
        firstname = request.form.get('firstname')
        lastname = request.form.get('lastname')
        password = request.form.get('password')
        role = request.form.get('role')
        access_all_branches = request.form.get('access_all_branches')
        selected_branches = request.form.getlist('selected_branches')
        
        # Basic validation
        if not email or not firstname or not lastname or not password or not role:
            flash('All fields are required', 'error')
            return redirect(url_for('add_user'))
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists. Please use a different email.', 'error')
            return redirect(url_for('add_user'))
        
        # Create new user
        new_user = User(
            email=email,
            firstname=firstname,
            lastname=lastname,
            password='',  # Will be set securely below
            role=role
        )
        new_user.set_password(password)  # Hash the password securely
        
        # Handle branch access
        if access_all_branches == 'on':
            new_user.set_all_branch_access()
        else:
            if selected_branches:
                # Convert string IDs to integers
                branch_ids = [int(bid) for bid in selected_branches if bid.isdigit()]
                new_user.accessible_branch_ids = branch_ids
            else:
                new_user.clear_branch_access()
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the user. Please try again.', 'error')
            return redirect(url_for('add_user'))
    
    # Get all branches for the form
    branches = Branch.query.order_by(Branch.name).all()
    return render_template('add_user.html', branches=branches)

@app.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        # Get form data
        email = request.form.get('email')
        firstname = request.form.get('firstname')
        lastname = request.form.get('lastname')
        password = request.form.get('password')
        role = request.form.get('role')
        access_all_branches = request.form.get('access_all_branches')
        selected_branches = request.form.getlist('selected_branches')
        
        # Basic validation
        if not email or not firstname or not lastname or not role:
            flash('Email, First Name, Last Name, and Role are required', 'error')
            return redirect(url_for('edit_user', id=id))
        
        # Check if email already exists (excluding current user)
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.id != id:
            flash('Email already exists. Please use a different email.', 'error')
            return redirect(url_for('edit_user', id=id))
        
        # Update user
        user.email = email
        user.firstname = firstname
        user.lastname = lastname
        user.role = role
        
        # Update password only if provided
        if password:
            user.set_password(password)  # Hash the password securely
        
        # Handle branch access
        if access_all_branches == 'on':
            user.set_all_branch_access()
        else:
            if selected_branches:
                # Convert string IDs to integers
                branch_ids = [int(bid) for bid in selected_branches if bid.isdigit()]
                user.accessible_branch_ids = branch_ids
            else:
                user.clear_branch_access()
        
        try:
            db.session.commit()
            flash('User updated successfully', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the user. Please try again.', 'error')
            return redirect(url_for('edit_user', id=id))
    
    # Get all branches for the form
    branches = Branch.query.order_by(Branch.name).all()
    return render_template('edit_user.html', user=user, branches=branches)

@app.route('/delete_user/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_user(id):
    try:
        user = User.query.get_or_404(id)
        
        # Prevent deleting the current user
        if user.id == current_user.id:
            flash('You cannot delete your own account.', 'error')
            return redirect(url_for('users'))
        
        # Check if user has related records
        if user.orders or user.stock_transactions or user.payments:
            flash('Cannot delete this user. They have associated orders, stock transactions, or payments.', 'error')
            return redirect(url_for('users'))
        
        db.session.delete(user)
        db.session.commit()
        
        flash('User deleted successfully', 'success')
        return redirect(url_for('users'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this user. They have associated data that prevents deletion.', 'error')
        return redirect(url_for('users'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the user. Please try again.', 'error')
        return redirect(url_for('users'))

# Orders Routes
@app.route('/orders')
@login_required
@role_required(['admin'])
def orders():
    try:
        print("Orders route accessed")
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Filter parameters
        status_filter = request.args.get('status', '')
        payment_filter = request.args.get('payment_status', '')
        branch_filter = request.args.get('branch_id', type=int)
        
        # Base query with joins and eager loading
        base_query = db.session.query(Order).options(
            db.joinedload(Order.user),
            db.joinedload(Order.ordertype),
            db.joinedload(Order.branch),
            # Legacy product relationship removed - using branch_product only
            db.joinedload(Order.order_items).joinedload(OrderItem.branch_product).joinedload(BranchProduct.catalog_product)
        )
        
        # Apply filters
        if status_filter:
            if status_filter == 'approved':
                base_query = base_query.filter(Order.approvalstatus == True)
            elif status_filter == 'pending':
                base_query = base_query.filter(Order.approvalstatus == False)
        
        if payment_filter:
            base_query = base_query.filter(Order.payment_status == payment_filter)
        
        if branch_filter:
            base_query = base_query.filter(Order.branchid == branch_filter)
        
        # Order by creation date (newest first)
        base_query = base_query.order_by(Order.created_at.desc())
        
        # Apply pagination
        pagination = base_query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        orders = pagination.items
        print(f"Orders found: {len(orders)}")
        
        # Debug: Check the first order's data
        if orders:
            first_order = orders[0]
            print(f"First order ID: {first_order.id}")
            print(f"First order user: {first_order.user.firstname if first_order.user else 'No user'}")
            print(f"First order branch: {first_order.branch.name if first_order.branch else 'No branch'}")
            print(f"First order items count: {len(first_order.order_items) if first_order.order_items else 0}")
            
            if first_order.order_items:
                first_item = first_order.order_items[0]
                print(f"First item product: {first_item.branch_product.catalog_product.name if first_item.branch_product and first_item.branch_product.catalog_product else 'No product'}")
                print(f"First item final_price: {first_item.final_price}")
                print(f"First item product sellingprice: {first_item.branch_product.sellingprice if first_item.branch_product else 'No product'}")
        
        # Calculate and update payment status for all orders
        for order in orders:
            print(f"\nCalculating total for order {order.id}:")
            # Calculate order total
            total_amount = 0
            for item in order.order_items:
                print(f"  Item {item.id}: quantity={item.quantity}, final_price={item.final_price}")
                
                # Handle both cases: products with relationships and manually entered items
                if item.final_price:
                    # Use the final_price if available (for manually entered items or negotiated prices)
                    item_total = item.final_price * item.quantity
                    total_amount += item_total
                    print(f"    Using final_price: {item.final_price} * {item.quantity} = {item_total}")
                elif item.branch_product and item.branch_product.sellingprice:
                    # Use branch product's selling price if no final_price but branch product relationship exists
                    item_total = item.branch_product.sellingprice * item.quantity
                    total_amount += item_total
                    print(f"    Using branch_product.sellingprice: {item.branch_product.sellingprice} * {item.quantity} = {item_total}")
                elif hasattr(item, 'product_name') and item.product_name:
                    # For manually entered items without product relationship, check if they have a price
                    if item.original_price:
                        item_total = item.original_price * item.quantity
                        total_amount += item_total
                        print(f"    Using original_price for manual item '{item.product_name}': {item.original_price} * {item.quantity} = {item_total}")
                    else:
                        print(f"    Manual item '{item.product_name}' has no price available")
                else:
                    print(f"    No price available for item {item.id}")
            
            print(f"  Order {order.id} total: {total_amount}")
            # Store the calculated total on the order object for template use
            order.calculated_total = total_amount
            
            # Calculate profit for the order using OrderItem fields directly
            order_profit = 0
            print(f"🔍 Calculating profit for order {order.id} with {len(order.order_items)} items")
            for item in order.order_items:
                print(f"  📦 Item {item.id}: final_price={item.final_price}, buying_price={item.buying_price}")
                
                # Use final_price as selling price and buying_price from OrderItem table
                if item.final_price and item.buying_price:
                    item_profit = (item.final_price - item.buying_price) * item.quantity
                    order_profit += item_profit
                    print(f"    💰 Profit: ({item.final_price} - {item.buying_price}) × {item.quantity} = {item_profit}")
                else:
                    print(f"    ⚠️ Cannot calculate profit - missing price data")
                    print(f"      final_price: {item.final_price}")
                    print(f"      buying_price: {item.buying_price}")
            
            # Store the calculated profit on the order object for template use
            order.calculated_profit = order_profit
            print(f"🔍 Order {order.id}: calculated_profit = {order_profit}")
            
            # Calculate total payments received
            total_payments = Decimal('0')
            for payment in order.payments:
                if payment.payment_status == 'completed':
                    total_payments += Decimal(str(payment.amount))
            
            # Determine payment status
            if total_payments >= total_amount:
                payment_status = 'paid'
            elif total_payments > 0:
                payment_status = 'partially_paid'
            else:
                payment_status = 'not_paid'
            
            # Update the order's payment_status field if it's different
            if order.payment_status != payment_status:
                order.payment_status = payment_status
        
        # Commit all payment status updates
        try:
            db.session.commit()
        except Exception as e:
            print(f"Error updating payment statuses: {e}")
            db.session.rollback()
        
        # Add adjusted times (3 hours ahead) for display
        for order in orders:
            order.created_at_adjusted = order.created_at + timedelta(hours=3)
            if order.approved_at:
                order.approved_at_adjusted = order.approved_at + timedelta(hours=3)
        
        # Get filter options
        branches = Branch.query.order_by(Branch.name).all()
        
        # Calculate order statistics (using the same filters as the main query)
        stats_query = db.session.query(Order)
        
        # Apply the same filters for statistics
        if status_filter:
            if status_filter == 'approved':
                stats_query = stats_query.filter(Order.approvalstatus == True)
            elif status_filter == 'pending':
                stats_query = stats_query.filter(Order.approvalstatus == False)
        
        if payment_filter:
            stats_query = stats_query.filter(Order.payment_status == payment_filter)
        
        if branch_filter:
            stats_query = stats_query.filter(Order.branchid == branch_filter)
        
        # Calculate statistics
        total_orders = stats_query.count()
        paid_orders = stats_query.filter(Order.payment_status == 'paid').count()
        pending_orders = stats_query.filter(Order.approvalstatus == False).count()
        
        # Calculate total revenue (only from paid orders)
        total_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).join(Order, OrderItem.orderid == Order.id).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            OrderItem.final_price.isnot(None)
        )
        
        # Apply same filters to revenue calculation
        if status_filter:
            if status_filter == 'approved':
                total_revenue = total_revenue.filter(Order.approvalstatus == True)
            elif status_filter == 'pending':
                total_revenue = total_revenue.filter(Order.approvalstatus == False)
        
        if branch_filter:
            total_revenue = total_revenue.filter(Order.branchid == branch_filter)
        
        total_revenue = total_revenue.scalar() or 0.0
        
        # Calculate profit statistics
        # Total profit calculation (all time)
        total_profit_query = db.session.query(
            db.func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity)
        ).join(Order, OrderItem.orderid == Order.id).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            OrderItem.final_price.isnot(None),
            OrderItem.buying_price.isnot(None)
        )
        
        # Apply same filters to profit calculation
        if status_filter:
            if status_filter == 'approved':
                total_profit_query = total_profit_query.filter(Order.approvalstatus == True)
            elif status_filter == 'pending':
                total_profit_query = total_profit_query.filter(Order.approvalstatus == False)
        
        if branch_filter:
            total_profit_query = total_profit_query.filter(Order.branchid == branch_filter)
        
        total_profit = total_profit_query.scalar() or 0.0
        
        # Monthly profit calculation (current month)
        current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_profit_query = db.session.query(
            db.func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity)
        ).join(Order, OrderItem.orderid == Order.id).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            OrderItem.final_price.isnot(None),
            OrderItem.buying_price.isnot(None),
            Order.created_at >= current_month_start
        )
        
        # Apply same filters to monthly profit calculation
        if status_filter:
            if status_filter == 'approved':
                monthly_profit_query = monthly_profit_query.filter(Order.approvalstatus == True)
            elif status_filter == 'pending':
                monthly_profit_query = monthly_profit_query.filter(Order.approvalstatus == False)
        
        if branch_filter:
            monthly_profit_query = monthly_profit_query.filter(Order.branchid == branch_filter)
        
        monthly_profit = monthly_profit_query.scalar() or 0.0
        
        return render_template('orders.html', 
                             orders=orders, 
                             pagination=pagination,
                             branches=branches,
                             status_filter=status_filter,
                             payment_filter=payment_filter,
                             branch_filter=branch_filter,
                             total_orders=total_orders,
                             paid_orders=paid_orders,
                             pending_orders=pending_orders,
                             total_revenue=float(total_revenue),
                             total_profit=float(total_profit),
                             monthly_profit=float(monthly_profit))
    except Exception as e:
        print(f"Error in orders route: {e}")
        db.session.rollback()
        flash('An error occurred while loading orders. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/order_details/<int:order_id>')
@login_required
@role_required(['admin'])
def order_details(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        
        # Calculate order total and profit using OrderItem fields directly
        total_amount = 0
        order_profit = 0
        for item in order.order_items:
            if item.final_price:
                total_amount += item.final_price * item.quantity
                
            # Calculate profit using final_price and buying_price from OrderItem table
            if item.final_price and item.buying_price:
                item_profit = (item.final_price - item.buying_price) * item.quantity
                order_profit += item_profit
        
        # Calculate payment status based on actual payments received
        total_payments = Decimal('0')
        for payment in order.payments:
            if payment.payment_status == 'completed':
                total_payments += Decimal(str(payment.amount))
        
        # Determine payment status
        if total_payments >= total_amount:
            payment_status = 'paid'
        elif total_payments > 0:
            payment_status = 'partially_paid'
        else:
            payment_status = 'not_paid'
        
        # Update the order's payment_status field
        if order.payment_status != payment_status:
            order.payment_status = payment_status
            try:
                db.session.commit()
            except Exception as e:
                print(f"Error updating payment status: {e}")
                db.session.rollback()
        
        # Add adjusted times (3 hours ahead) for display
        
        # Create adjusted time attributes for the order
        order.created_at_adjusted = order.created_at + timedelta(hours=3)
        if order.approved_at:
            order.approved_at_adjusted = order.approved_at + timedelta(hours=3)
        
        # Create adjusted time attributes for payments
        for payment in order.payments:
            payment.created_at_adjusted = payment.created_at + timedelta(hours=3)
        
        return render_template('order_details.html', order=order, total_amount=total_amount, total_payments=total_payments, payment_status=payment_status, total_profit=order_profit)
    except Exception as e:
        print(f"Error in order details route: {e}")
        flash('An error occurred while loading order details.', 'error')
        return redirect(url_for('orders'))

@app.route('/approve_order/<int:order_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def approve_order(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        order.approvalstatus = True
        order.approved_at = datetime.now(EAT)
        db.session.commit()
        
        flash(f'Order #{order.id} has been approved successfully.', 'success')
        return redirect(url_for('orders'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the order.', 'error')
        return redirect(url_for('orders'))

@app.route('/reject_order/<int:order_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def reject_order(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        order.approvalstatus = False
        order.approved_at = None
        db.session.commit()
        
        flash(f'Order #{order.id} has been rejected.', 'success')
        return redirect(url_for('orders'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the order.', 'error')
        return redirect(url_for('orders'))

# Profit & Loss Routes
@app.route('/profit_loss')
@login_required
@role_required(['admin'])
def profit_loss():
    try:
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Default to current month if no dates provided
        if not start_date:
            start_date = datetime.now(EAT).replace(day=1).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now(EAT).strftime('%Y-%m-%d')
        
        # Convert to datetime objects
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Calculate Revenue (from completed orders)
        # Use BranchProduct for new orders, fallback to ProductCatalog for legacy orders
        revenue_query = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        )
        total_revenue = revenue_query.scalar() or 0
        
        # Calculate Cost of Goods Sold (COGS)
        # Use BranchProduct buying price for new orders, fallback to ProductCatalog for legacy orders
        cogs_query = db.session.query(
            db.func.sum(OrderItem.quantity * db.func.coalesce(BranchProduct.buyingprice, ProductCatalog.buyingprice, 0))
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        )
        total_cogs = cogs_query.scalar() or 0
        
        # Calculate Gross Profit
        gross_profit = total_revenue - total_cogs
        
        # Calculate Total Expenses (approved expenses only)
        total_expenses = db.session.query(
            db.func.sum(Expense.amount)
        ).filter(
            Expense.status == 'approved',
            Expense.expense_date >= start_dt.date(),
            Expense.expense_date <= end_dt.date()
        ).scalar() or 0
        
        # Calculate Net Profit
        net_profit = gross_profit - total_expenses
        
        # Get expense breakdown by category
        expenses_by_category = db.session.query(
            Expense.category,
            db.func.sum(Expense.amount).label('total_amount'),
            db.func.count(Expense.id).label('count')
        ).filter(
            Expense.status == 'approved',
            Expense.expense_date >= start_dt.date(),
            Expense.expense_date <= end_dt.date()
        ).group_by(Expense.category).order_by(
            db.func.sum(Expense.amount).desc()
        ).all()
        
        # Get order statistics
        total_orders = Order.query.filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).count()
        
        paid_orders = Order.query.filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).count()
        
        # Get top selling products
        # Use BranchProduct for new orders, fallback to ProductCatalog for legacy orders
        top_products = db.session.query(
            db.func.coalesce(ProductCatalog.name, ProductCatalog.name).label('product_name'),
            db.func.sum(OrderItem.quantity).label('total_quantity'),
            db.func.sum(OrderItem.quantity * OrderItem.final_price).label('total_revenue')
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, BranchProduct.catalog_id == ProductCatalog.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).group_by(db.func.coalesce(ProductCatalog.name, ProductCatalog.name)).order_by(
            db.func.sum(OrderItem.quantity).desc()
        ).limit(10).all()
        
        # Top products by asset value (buying price * stock)
        top_products_by_asset_value = db.session.query(
            ProductCatalog, (ProductCatalog.buyingprice * ProductCatalog.stock).label('asset_value')
        ).filter(
            and_(
                ProductCatalog.buyingprice.isnot(None),
                ProductCatalog.buyingprice > 0,
                ProductCatalog.stock.isnot(None),
                ProductCatalog.stock > 0
            )
        ).order_by((ProductCatalog.buyingprice * ProductCatalog.stock).desc()).limit(5).all()
        
        # Calculate total product asset for percentage calculation
        total_product_asset = db.session.query(
            func.sum(BranchProduct.buyingprice * BranchProduct.stock)
        ).filter(
            and_(
                BranchProduct.buyingprice.isnot(None),
                BranchProduct.buyingprice > 0,
                BranchProduct.stock.isnot(None),
                BranchProduct.stock > 0
            )
        ).scalar() or 0
        
        # Calculate percentage of total assets for each top product
        top_products_with_percentage = []
        for product, asset_value in top_products_by_asset_value:
            percentage = (asset_value / total_product_asset * 100) if total_product_asset > 0 else 0
            top_products_with_percentage.append({
                'product': product,
                'asset_value': asset_value,
                'percentage': percentage
            })
        
        # Calculate profit margins
        gross_profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return render_template('profit_loss.html',
                             start_date=start_date,
                             end_date=end_date,
                             total_revenue=total_revenue,
                             total_cogs=total_cogs,
                             gross_profit=gross_profit,
                             total_expenses=total_expenses,
                             net_profit=net_profit,
                             gross_profit_margin=gross_profit_margin,
                             net_profit_margin=net_profit_margin,
                             total_orders=total_orders,
                             paid_orders=paid_orders,
                             top_products=top_products,
                             top_products_by_asset_value=top_products_by_asset_value,
                             top_products_with_percentage=top_products_with_percentage,
                             expenses_by_category=expenses_by_category)
    except Exception as e:
        print(f"Error in profit_loss route: {e}")
        flash('An error occurred while loading profit & loss data.', 'error')
        return redirect(url_for('index'))

@app.route('/balance_sheet')
@login_required
@role_required(['admin'])
def balance_sheet():
    try:
        # Get date as of which to show balance sheet
        as_of_date = request.args.get('as_of_date')
        if not as_of_date:
            as_of_date = datetime.now(EAT).strftime('%Y-%m-%d')
        
        as_of_dt = datetime.strptime(as_of_date, '%Y-%m-%d')
        
        # Calculate Assets
        # Inventory Value (current stock * buying price)
        # Use BranchProduct for new inventory, fallback to ProductCatalog for legacy inventory
        inventory_value = db.session.query(
            db.func.sum(db.func.coalesce(BranchProduct.stock * BranchProduct.buyingprice, ProductCatalog.stock * ProductCatalog.buyingprice, 0))
        ).outerjoin(BranchProduct, True).outerjoin(ProductCatalog, True).filter(
            db.or_(BranchProduct.stock > 0, ProductCatalog.stock > 0)
        ).scalar() or 0
        
        # Accounts Receivable (pending payments)
        accounts_receivable = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'pending',
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        # Cash (completed payments)
        cash = db.session.query(
            db.func.sum(Payment.amount)
        ).filter(
            Payment.payment_status == 'completed',
            Payment.created_at <= as_of_dt
        ).scalar() or 0
        
        total_assets = inventory_value + accounts_receivable + cash
        
        # Calculate Liabilities
        # Accounts Payable (simplified - could be enhanced with actual supplier data)
        accounts_payable = 0  # Placeholder for actual supplier payables
        
        # Calculate Equity
        # Retained Earnings (simplified calculation)
        total_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        total_cogs = db.session.query(
            db.func.sum(OrderItem.quantity * db.func.coalesce(BranchProduct.buyingprice, ProductCatalog.buyingprice, 0))
        ).select_from(OrderItem).outerjoin(BranchProduct, OrderItem.branch_productid == BranchProduct.id).outerjoin(ProductCatalog, OrderItem.productid == ProductCatalog.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status.in_(['paid', 'partially_paid']),
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        # Calculate total expenses up to the balance sheet date
        total_expenses = db.session.query(
            db.func.sum(Expense.amount)
        ).filter(
            Expense.status == 'approved',
            Expense.expense_date <= as_of_dt.date()
        ).scalar() or 0
        
        # Retained Earnings = Revenue - COGS - Expenses
        retained_earnings = total_revenue - total_cogs - total_expenses
        
        total_liabilities_equity = accounts_payable + retained_earnings
        
        # Get inventory breakdown by category
        inventory_by_category = db.session.query(
            Category.name,
            db.func.sum(ProductCatalog.stock * ProductCatalog.buyingprice).label('value')
        ).select_from(Category).join(SubCategory, Category.id == SubCategory.category_id).join(
            ProductCatalog, SubCategory.id == ProductCatalog.subcategory_id
        ).filter(ProductCatalog.stock > 0).group_by(Category.id, Category.name).all()
        
        # Get recent transactions
        recent_transactions = db.session.query(
            Order, User, Branch
        ).select_from(Order).join(User, Order.userid == User.id).join(
            Branch, Order.branchid == Branch.id
        ).filter(
            Order.created_at <= as_of_dt
        ).order_by(Order.created_at.desc()).limit(10).all()
        
        return render_template('balance_sheet.html',
                             as_of_date=as_of_date,
                             inventory_value=inventory_value,
                             accounts_receivable=accounts_receivable,
                             cash=cash,
                             total_assets=total_assets,
                             accounts_payable=accounts_payable,
                             retained_earnings=retained_earnings,
                             total_liabilities_equity=total_liabilities_equity,
                             inventory_by_category=inventory_by_category,
                             recent_transactions=recent_transactions)
    except Exception as e:
        print(f"Error in balance_sheet route: {e}")
        flash('An error occurred while loading balance sheet data.', 'error')
        return redirect(url_for('index'))

# Branch Management Routes
@app.route('/branches')
@login_required
@role_required(['admin'])
def branches():
    try:
        print("Branches route accessed")
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get branches with simple pagination
        pagination = Branch.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        branches = pagination.items
        print(f"Branches found: {len(branches)}")
        
        # Get branch statistics in bulk queries for better performance
        branch_ids = [branch.id for branch in branches]
        
        # Get product counts for all branches in one query
        product_counts = db.session.query(
            BranchProduct.branchid,
            db.func.count(BranchProduct.id).label('product_count')
        ).filter(BranchProduct.branchid.in_(branch_ids)).group_by(BranchProduct.branchid).all()
        product_count_dict = {bid: count for bid, count in product_counts}
        
        # Get order counts for all branches in one query
        order_counts = db.session.query(
            Order.branchid,
            db.func.count(Order.id).label('order_count')
        ).filter(Order.branchid.in_(branch_ids)).group_by(Order.branchid).all()
        order_count_dict = {bid: count for bid, count in order_counts}
        
        # Get revenue for all branches in one efficient query
        revenue_data = db.session.query(
            Order.branchid,
            db.func.sum(OrderItem.quantity * OrderItem.final_price).label('revenue')
        ).join(OrderItem, Order.id == OrderItem.orderid).filter(
            Order.branchid.in_(branch_ids),
            Order.payment_status.in_(['paid', 'partially_paid']),
            OrderItem.final_price.isnot(None)
        ).group_by(Order.branchid).all()
        revenue_dict = {bid: float(revenue) if revenue else 0.0 for bid, revenue in revenue_data}
        
        # Add calculated attributes to branch objects
        for branch in branches:
            branch.product_count = product_count_dict.get(branch.id, 0)
            branch.order_count = order_count_dict.get(branch.id, 0)
            branch.revenue = revenue_dict.get(branch.id, 0.0)
        
        return render_template('branches.html', branches=branches, pagination=pagination)
    except Exception as e:
        print(f"Error in branches route: {e}")
        db.session.rollback()
        flash('An error occurred while loading branches. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/debug_payment_status')
@login_required
@role_required(['admin'])
def debug_payment_status():
    try:
        # Get all orders with their payment status
        orders = Order.query.all()
        debug_info = []
        
        for order in orders:
            # Calculate order total
            total_amount = 0
            for item in order.order_items:
                if item.final_price:
                    total_amount += item.final_price * item.quantity
                # Legacy product relationship removed - using branch_product only
            
            # Calculate total payments received
            total_payments = Decimal('0')
            for payment in order.payments:
                if payment.payment_status == 'completed':
                    total_payments += Decimal(str(payment.amount))
            
            # Determine payment status
            if total_payments >= total_amount:
                payment_status = 'paid'
            elif total_payments > 0:
                payment_status = 'partially_paid'
            else:
                payment_status = 'not_paid'
            
            debug_info.append({
                'order_id': order.id,
                'current_status': order.payment_status,
                'calculated_status': payment_status,
                'total_amount': total_amount,
                'total_payments': total_payments,
                'payment_count': len(order.payments)
            })
        
        return jsonify(debug_info)
        
    except Exception as e:
        print(f"Error in debug route: {e}")
        return jsonify({'error': str(e)})

@app.route('/debug_branches_revenue')
@login_required
@role_required(['admin'])
def debug_branches_revenue():
    try:
        branches = Branch.query.all()
        debug_info = []
        
        for branch in branches:
            # Calculate branch revenue
            branch_revenue = 0
            for order in branch.orders:
                if order.payment_status in ['paid', 'partially_paid']:
                    for item in order.order_items:
                        if item.final_price:
                            branch_revenue += float(item.final_price * item.quantity)
                        elif item.branch_product and item.branch_product.sellingprice:
                            branch_revenue += float(item.branch_product.sellingprice * item.quantity)
            
            branch_data = {
                'branch_id': branch.id,
                'branch_name': branch.name,
                'orders_count': len(branch.orders),
                'revenue': branch_revenue,
                'orders': []
            }
            
            for order in branch.orders:
                order_data = {
                    'order_id': order.id,
                    'payment_status': order.payment_status,
                    'payments_count': len(order.payments),
                    'payments': []
                }
                
                for payment in order.payments:
                    payment_data = {
                        'payment_id': payment.id,
                        'amount': float(payment.amount) if payment.amount else 0,
                        'payment_status': payment.payment_status,
                        'payment_method': payment.payment_method
                    }
                    order_data['payments'].append(payment_data)
                
                branch_data['orders'].append(order_data)
            
            debug_info.append(branch_data)
        
        return jsonify(debug_info)
        
    except Exception as e:
        print(f"Error in debug branches revenue route: {e}")
        return jsonify({'error': str(e)})

@app.route('/add_branch', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_branch():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        location = request.form.get('location')
        
        # Basic validation
        if not name or not location:
            flash('Branch name and location are required', 'error')
            return redirect(url_for('add_branch'))
        
        # Check if branch name already exists
        existing_branch = Branch.query.filter_by(name=name).first()
        if existing_branch:
            flash('Branch name already exists. Please use a different name.', 'error')
            return redirect(url_for('add_branch'))
        
        # Create new branch
        new_branch = Branch(
            name=name,
            location=location
        )
        
        try:
            db.session.add(new_branch)
            db.session.commit()
            flash('Branch added successfully', 'success')
            return redirect(url_for('branches'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the branch. Please try again.', 'error')
            return redirect(url_for('add_branch'))
    
    return render_template('add_branch.html')

@app.route('/edit_branch/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_branch(id):
    branch = Branch.query.get_or_404(id)
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        location = request.form.get('location')
        
        # Basic validation
        if not name or not location:
            flash('Branch name and location are required', 'error')
            return redirect(url_for('edit_branch', id=id))
        
        # Check if branch name already exists (excluding current branch)
        existing_branch = Branch.query.filter_by(name=name).first()
        if existing_branch and existing_branch.id != id:
            flash('Branch name already exists. Please use a different name.', 'error')
            return redirect(url_for('edit_branch', id=id))
        
        # Update branch
        branch.name = name
        branch.location = location
        
        try:
            db.session.commit()
            flash('Branch updated successfully', 'success')
            return redirect(url_for('branches'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the branch. Please try again.', 'error')
            return redirect(url_for('edit_branch', id=id))
    
    return render_template('edit_branch.html', branch=branch)

@app.route('/delete_branch/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_branch(id):
    try:
        branch = Branch.query.get_or_404(id)
        
        # Check if branch has related records
        if branch.branch_products or branch.orders:
            flash('Cannot delete this branch. It has associated products or orders.', 'error')
            return redirect(url_for('branches'))
        
        db.session.delete(branch)
        db.session.commit()
        
        flash('Branch deleted successfully', 'success')
        return redirect(url_for('branches'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this branch. It has associated data that prevents deletion.', 'error')
        return redirect(url_for('branches'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the branch. Please try again.', 'error')
        return redirect(url_for('branches'))

@app.route('/branch_details/<int:branch_id>')
@login_required
@role_required(['admin'])
def branch_details(branch_id):
    try:
        branch = Branch.query.get_or_404(branch_id)
        
        # Get branch statistics
        total_products = BranchProduct.query.filter_by(branchid=branch_id).count()
        total_orders = Order.query.filter_by(branchid=branch_id).count()
        
        # Get recent orders for this branch
        recent_orders = Order.query.filter_by(branchid=branch_id).order_by(Order.created_at.desc()).limit(10).all()
        
        # Get only a limited number of products for display (for performance)
        products = BranchProduct.query.filter_by(branchid=branch_id).limit(20).all()
        
        # Calculate branch revenue using the same efficient method as branches page
        branch_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).join(Order, OrderItem.orderid == Order.id).filter(
            Order.branchid == branch_id,
            Order.payment_status.in_(['paid', 'partially_paid']),
            OrderItem.final_price.isnot(None)
        ).scalar() or 0
        
        return render_template('branch_details.html', 
                             branch=branch,
                             total_products=total_products,
                             total_orders=total_orders,
                             recent_orders=recent_orders,
                             products=products,
                             branch_revenue=branch_revenue)
    except Exception as e:
        print(f"Error in branch details route: {e}")
        flash('An error occurred while loading branch details.', 'error')
        return redirect(url_for('branches'))

# Category Management Routes
@app.route('/categories')
@login_required
@role_required(['admin'])
def categories():
    try:
        import time
        start_time = time.time()
        print("Categories route accessed")
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get all categories with pagination and eager loading
        pagination = Category.query.options(
            db.joinedload(Category.sub_categories)
        ).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        categories = pagination.items
        print(f"Categories found: {len(categories)}")
        
        # Pre-calculate product counts and revenue for all categories in efficient queries
        category_ids = [cat.id for cat in categories]
        print(f"Processing {len(category_ids)} categories: {category_ids}")
        
        try:
            # Method 1: Try complex joins first
            try:
                # Get product counts for all categories in one query
                product_counts = db.session.query(
                    SubCategory.category_id,
                    db.func.count(ProductCatalog.id).label('product_count')
                ).select_from(SubCategory).outerjoin(
                    ProductCatalog, SubCategory.id == ProductCatalog.subcategory_id
                ).filter(
                    SubCategory.category_id.in_(category_ids)
                ).group_by(SubCategory.category_id).all()
                
                print(f"ProductCatalog counts query result: {product_counts}")
                
                # Convert to dictionary for easy lookup
                product_count_dict = {cat_id: count for cat_id, count in product_counts}
                
                # Get revenue for all categories in one query
                revenue_data = db.session.query(
                    SubCategory.category_id,
                    db.func.sum(OrderItem.quantity * OrderItem.final_price).label('revenue')
                ).select_from(SubCategory).join(
                    ProductCatalog, SubCategory.id == ProductCatalog.subcategory_id
                ).join(
                    OrderItem, ProductCatalog.id == OrderItem.productid
                ).join(
                    Order, OrderItem.orderid == Order.id
                ).filter(
                    SubCategory.category_id.in_(category_ids),
                    Order.payment_status.in_(['paid', 'partially_paid']),
                    OrderItem.final_price.isnot(None)
                ).group_by(SubCategory.category_id).all()
                
                print(f"Revenue query result: {revenue_data}")
                
                # Convert to dictionary for easy lookup
                revenue_dict = {cat_id: float(revenue) if revenue else 0.0 for cat_id, revenue in revenue_data}
                
            except Exception as join_error:
                print(f"Complex join failed, using simple approach: {join_error}")
                # Method 2: Simple approach - calculate for each category individually
                product_count_dict = {}
                revenue_dict = {}
                
                for category in categories:
                    # Get subcategories for this category
                    subcategories = SubCategory.query.filter_by(category_id=category.id).all()
                    subcategory_ids = [sub.id for sub in subcategories]
                    
                    if subcategory_ids:
                        # Count products
                        product_count = ProductCatalog.query.filter(ProductCatalog.subcategory_id.in_(subcategory_ids)).count()
                        product_count_dict[category.id] = product_count
                        
                        # Calculate revenue
                        revenue = db.session.query(
                            db.func.sum(OrderItem.quantity * OrderItem.final_price)
                        ).join(ProductCatalog).join(Order).filter(
                            ProductCatalog.subcategory_id.in_(subcategory_ids),
                            Order.payment_status.in_(['paid', 'partially_paid']),
                            OrderItem.final_price.isnot(None)
                        ).scalar() or 0
                        revenue_dict[category.id] = float(revenue)
                    else:
                        product_count_dict[category.id] = 0
                        revenue_dict[category.id] = 0.0
            
            # Add calculated values to category objects
            for category in categories:
                category.product_count = product_count_dict.get(category.id, 0)
                category.calculated_revenue = revenue_dict.get(category.id, 0.0)
            
            # Calculate summary totals efficiently
            total_products = sum(product_count_dict.values())
            total_revenue = sum(revenue_dict.values())
            avg_products_per_category = total_products / len(categories) if categories else 0
            
        except Exception as e:
            print(f"Error in data calculation: {e}")
            # Fallback to simple values if queries fail
            for category in categories:
                category.product_count = 0
                category.calculated_revenue = 0.0
            
            total_products = 0
            total_revenue = 0.0
            avg_products_per_category = 0.0
        
        execution_time = time.time() - start_time
        print(f"Categories route executed in {execution_time:.2f} seconds")
        
        return render_template('categories.html', 
                             categories=categories, 
                             pagination=pagination,
                             total_products=total_products,
                             total_revenue=total_revenue,
                             avg_products_per_category=avg_products_per_category)
    except Exception as e:
        print(f"Error in categories route: {e}")
        db.session.rollback()
        flash('An error occurred while loading categories. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/category_details/<int:category_id>')
@login_required
@role_required(['admin'])
def category_details(category_id):
    try:
        category = Category.query.get_or_404(category_id)
        
        # Get subcategories for this category
        subcategories = SubCategory.query.filter_by(category_id=category_id).order_by(SubCategory.name).all()
        subcategory_ids = [sub.id for sub in subcategories]
        
        # Handle both old and new product structures
        if subcategory_ids:
            # New structure: products through subcategories
            total_products = ProductCatalog.query.filter(ProductCatalog.subcategory_id.in_(subcategory_ids)).count()
            products = ProductCatalog.query.filter(ProductCatalog.subcategory_id.in_(subcategory_ids)).order_by(ProductCatalog.id).all()
            
            # Calculate category revenue
            category_revenue = db.session.query(
                db.func.sum(OrderItem.quantity * OrderItem.final_price)
            ).join(ProductCatalog).join(Order).filter(
                ProductCatalog.subcategory_id.in_(subcategory_ids),
                Order.payment_status.in_(['paid', 'partially_paid'])
            ).scalar() or 0
            
            # Get products by branch
            products_by_branch = db.session.query(
                Branch.name,
                db.func.count(ProductCatalog.id).label('product_count')
            ).join(ProductCatalog).filter(
                ProductCatalog.subcategory_id.in_(subcategory_ids)
            ).group_by(Branch.id, Branch.name).all()
        else:
            # No subcategories yet, show empty state
            total_products = 0
            products = []
            category_revenue = 0
            products_by_branch = []
        
        return render_template('category_details.html', 
                             category=category,
                             total_products=total_products,
                             products=products,
                             category_revenue=category_revenue,
                             products_by_branch=products_by_branch)
    except Exception as e:
        print(f"Error in category details route: {e}")
        flash('An error occurred while loading category details.', 'error')
        return redirect(url_for('categories'))

# Subcategory Management Routes
@app.route('/subcategories')
@login_required
@role_required(['admin'])
def subcategories():
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get all subcategories with pagination
        pagination = SubCategory.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        subcategories = pagination.items
        
        # Add adjusted times (3 hours ahead) for display
        for subcategory in subcategories:
            subcategory.created_at_adjusted = subcategory.created_at + timedelta(hours=3)
        
        return render_template('subcategories.html', subcategories=subcategories, pagination=pagination)
    except Exception as e:
        print(f"Error in subcategories route: {e}")
        db.session.rollback()
        flash('An error occurred while loading subcategories. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/add_subcategory', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_subcategory():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        
        if not name or not category_id:
            flash('Subcategory name and parent category are required', 'error')
            return redirect(url_for('add_subcategory'))
        
        # Check if subcategory name already exists in the same category
        existing_subcategory = SubCategory.query.filter_by(
            name=name, category_id=category_id
        ).first()
        if existing_subcategory:
            flash('Subcategory name already exists in this category. Please use a different name.', 'error')
            return redirect(url_for('add_subcategory'))
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                try:
                    image_url = upload_to_cloudinary(file)
                    if not image_url:
                        flash('Failed to upload image. Please try again.', 'error')
                        return redirect(url_for('add_subcategory'))
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
                    return redirect(url_for('add_subcategory'))
        
        new_subcategory = SubCategory(
            name=name,
            description=description,
            category_id=category_id,
            image_url=image_url
        )
        
        try:
            db.session.add(new_subcategory)
            db.session.commit()
            flash('Subcategory added successfully', 'success')
            return redirect(url_for('subcategories'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the subcategory. Please try again.', 'error')
            return redirect(url_for('add_subcategory'))
    
    # Get all categories for the dropdown
    categories = Category.query.order_by(Category.name).all()
    return render_template('add_subcategory.html', categories=categories)

@app.route('/edit_subcategory/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_subcategory(id):
    subcategory = SubCategory.query.get_or_404(id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        
        if not name or not category_id:
            flash('Subcategory name and parent category are required', 'error')
            return redirect(url_for('edit_subcategory', id=id))
        
        # Check if subcategory name already exists in the same category (excluding current)
        existing_subcategory = SubCategory.query.filter_by(
            name=name, category_id=category_id
        ).first()
        if existing_subcategory and existing_subcategory.id != id:
            flash('Subcategory name already exists in this category. Please use a different name.', 'error')
            return redirect(url_for('edit_subcategory', id=id))
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                try:
                    # Delete old image if exists
                    if subcategory.image_url:
                        delete_from_cloudinary(subcategory.image_url)
                    
                    image_url = upload_to_cloudinary(file)
                    if image_url:
                        subcategory.image_url = image_url
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
                    return redirect(url_for('edit_subcategory', id=id))
        
        # Update subcategory
        subcategory.name = name
        subcategory.description = description
        subcategory.category_id = category_id
        
        try:
            db.session.commit()
            flash('Subcategory updated successfully', 'success')
            return redirect(url_for('subcategories'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the subcategory. Please try again.', 'error')
            return redirect(url_for('edit_subcategory', id=id))
    
    # Get all categories for the dropdown
    categories = Category.query.order_by(Category.name).all()
    return render_template('edit_subcategory.html', subcategory=subcategory, categories=categories)

@app.route('/delete_subcategory/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_subcategory(id):
    try:
        subcategory = SubCategory.query.get_or_404(id)
        
        # Check if subcategory has related products
        if subcategory.products:
            flash('Cannot delete this subcategory. It has associated products.', 'error')
            return redirect(url_for('subcategories'))
        
        # Delete image from Cloudinary if exists
        if subcategory.image_url:
            delete_from_cloudinary(subcategory.image_url)
        
        db.session.delete(subcategory)
        db.session.commit()
        
        flash('Subcategory deleted successfully', 'success')
        return redirect(url_for('subcategories'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this subcategory. It has associated data that prevents deletion.', 'error')
        return redirect(url_for('subcategories'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the subcategory. Please try again.', 'error')
        return redirect(url_for('subcategories'))

@app.route('/subcategory_details/<int:subcategory_id>')
@login_required
@role_required(['admin'])
def subcategory_details(subcategory_id):
    try:
        subcategory = SubCategory.query.get_or_404(subcategory_id)
        
        # Get subcategory statistics
        total_products = ProductCatalog.query.filter_by(subcategory_id=subcategory_id).count()
        
        # Get products in this subcategory
        products = ProductCatalog.query.filter_by(subcategory_id=subcategory_id).all()
        
        # Calculate subcategory revenue
        subcategory_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * OrderItem.final_price)
        ).join(ProductCatalog).join(Order).filter(
            ProductCatalog.subcategory_id == subcategory_id,
            Order.payment_status.in_(['paid', 'partially_paid'])
        ).scalar() or 0
        
        # Get products by branch
        products_by_branch = db.session.query(
            Branch.name,
            db.func.count(ProductCatalog.id).label('product_count')
        ).join(ProductCatalog).filter(
            ProductCatalog.subcategory_id == subcategory_id
        ).group_by(Branch.id, Branch.name).all()
        
        return render_template('subcategory_details.html', 
                             subcategory=subcategory,
                             total_products=total_products,
                             products=products,
                             subcategory_revenue=subcategory_revenue,
                             products_by_branch=products_by_branch)
    except Exception as e:
        print(f"Error in subcategory details route: {e}")
        flash('An error occurred while loading subcategory details.', 'error')
        return redirect(url_for('subcategories'))

# ProductCatalog Description Management Routes
@app.route('/product_descriptions/<int:product_id>')
@login_required
@role_required(['admin'])
def product_descriptions(product_id):
    try:
        product = ProductCatalog.query.get_or_404(product_id)
        descriptions = ProductDescription.query.filter_by(
            product_id=product_id, is_active=True
        ).order_by(ProductDescription.sort_order, ProductDescription.created_at).all()
        
        # Add adjusted times (3 hours ahead) for display
        for description in descriptions:
            description.created_at_adjusted = description.created_at + timedelta(hours=3)
        
        return render_template('product_descriptions.html', 
                             product=product, 
                             descriptions=descriptions)
    except Exception as e:
        print(f"Error in product descriptions route: {e}")
        flash('An error occurred while loading product descriptions.', 'error')
        return redirect(url_for('products'))

@app.route('/add_product_description/<int:product_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_product_description(product_id):
    product = ProductCatalog.query.get_or_404(product_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        content_type = request.form.get('content_type', 'text')
        language = request.form.get('language', 'en')
        sort_order = int(request.form.get('sort_order', 0))
        
        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('add_product_description', product_id=product_id))
        
        new_description = ProductDescription(
            product_id=product_id,
            title=title,
            content=content,
            content_type=content_type,
            language=language,
            sort_order=sort_order
        )
        
        try:
            db.session.add(new_description)
            db.session.commit()
            flash('ProductCatalog description added successfully', 'success')
            return redirect(url_for('product_descriptions', product_id=product_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the description. Please try again.', 'error')
            return redirect(url_for('add_product_description', product_id=product_id))
    
    return render_template('add_product_description.html', product=product)

@app.route('/edit_product_description/<int:description_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_product_description(description_id):
    description = ProductDescription.query.get_or_404(description_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        content_type = request.form.get('content_type', 'text')
        language = request.form.get('language', 'en')
        sort_order = int(request.form.get('sort_order', 0))
        is_active = request.form.get('is_active') == 'on'
        
        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('edit_product_description', description_id=description_id))
        
        description.title = title
        description.content = content
        description.content_type = content_type
        description.language = language
        description.sort_order = sort_order
        description.is_active = is_active
        
        try:
            db.session.commit()
            flash('ProductCatalog description updated successfully', 'success')
            return redirect(url_for('product_descriptions', product_id=description.product_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the description. Please try again.', 'error')
            return redirect(url_for('edit_product_description', description_id=description_id))
    
    return render_template('edit_product_description.html', description=description)

@app.route('/delete_product_description/<int:description_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_product_description(description_id):
    try:
        description = ProductDescription.query.get_or_404(description_id)
        product_id = description.product_id
        
        db.session.delete(description)
        db.session.commit()
        
        flash('ProductCatalog description deleted successfully', 'success')
        return redirect(url_for('product_descriptions', product_id=product_id))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the description. Please try again.', 'error')
        return redirect(url_for('product_descriptions', product_id=description.product_id))


# Expense Management Routes
@app.route('/expenses')
@login_required
@role_required(['admin'])
def expenses():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Get filter parameters
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    branch_filter = request.args.get('branch', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = Expense.query
    
    if status_filter:
        query = query.filter(Expense.status == status_filter)
    if category_filter:
        query = query.filter(Expense.category == category_filter)
    if branch_filter:
        query = query.filter(Expense.branch_id == int(branch_filter))
    if date_from:
        query = query.filter(Expense.expense_date >= date_from)
    if date_to:
        query = query.filter(Expense.expense_date <= date_to)
    
    # Order by date (newest first)
    expenses = query.order_by(Expense.expense_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get unique categories and branches for filters
    categories = db.session.query(Expense.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('expenses.html', 
                         expenses=expenses,
                         categories=categories,
                         status_filter=status_filter,
                         category_filter=category_filter,
                         branch_filter=branch_filter,
                         date_from=date_from,
                         date_to=date_to)


@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_expense():
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            amount = request.form.get('amount')
            category = request.form.get('category')
            expense_date = request.form.get('expense_date')
            payment_method = request.form.get('payment_method')
            branch_id = request.form.get('branch_id')
            
            # Validation
            if not all([title, amount, category, expense_date]):
                flash('Please fill in all required fields.', 'danger')
                return redirect(url_for('add_expense'))
            
            # Handle receipt upload
            receipt_url = None
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    receipt_url = upload_to_cloudinary(file)
            
            # Create expense
            expense = Expense(
                title=title,
                description=description,
                amount=amount,
                category=category,
                expense_date=datetime.strptime(expense_date, '%Y-%m-%d').date(),
                payment_method=payment_method,
                receipt_url=receipt_url,
                branch_id=int(branch_id) if branch_id else None,
                user_id=current_user.id
            )
            
            db.session.add(expense)
            db.session.commit()
            
            flash('Expense added successfully!', 'success')
            return redirect(url_for('expenses'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding expense: {str(e)}', 'danger')
            return redirect(url_for('add_expense'))
    
    return render_template('add_expense.html')


@app.route('/edit_expense/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            expense.title = request.form.get('title')
            expense.description = request.form.get('description')
            expense.amount = request.form.get('amount')
            expense.category = request.form.get('category')
            expense.expense_date = datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d').date()
            expense.payment_method = request.form.get('payment_method')
            expense.branch_id = int(request.form.get('branch_id')) if request.form.get('branch_id') else None
            
            # Handle receipt upload
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    # Delete old receipt if exists
                    if expense.receipt_url:
                        delete_from_cloudinary(expense.receipt_url)
                    expense.receipt_url = upload_to_cloudinary(file)
            
            db.session.commit()
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('expenses'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'danger')
    
    # Add adjusted times (3 hours ahead) for display
    expense.created_at_adjusted = expense.created_at + timedelta(hours=3)
    expense.updated_at_adjusted = expense.updated_at + timedelta(hours=3)
    
    return render_template('edit_expense.html', expense=expense)


@app.route('/approve_expense/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def approve_expense(id):
    expense = Expense.query.get_or_404(id)
    
    try:
        expense.status = 'approved'
        expense.approved_by = current_user.id
        expense.approval_notes = request.form.get('approval_notes', '')
        expense.updated_at = datetime.now(EAT)
        
        db.session.commit()
        flash('Expense approved successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving expense: {str(e)}', 'danger')
    
    return redirect(url_for('expenses'))


@app.route('/reject_expense/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def reject_expense(id):
    expense = Expense.query.get_or_404(id)
    
    try:
        expense.status = 'rejected'
        expense.approved_by = current_user.id
        expense.approval_notes = request.form.get('approval_notes', '')
        expense.updated_at = datetime.now(EAT)
        
        db.session.commit()
        flash('Expense rejected successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting expense: {str(e)}', 'danger')
    
    return redirect(url_for('expenses'))


@app.route('/delete_expense/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    
    try:
        # Delete receipt image if exists
        if expense.receipt_url:
            delete_from_cloudinary(expense.receipt_url)
        
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting expense: {str(e)}', 'danger')
    
    return redirect(url_for('expenses'))


@app.route('/expense_details/<int:id>')
@login_required
@role_required(['admin'])
def expense_details(id):
    expense = Expense.query.get_or_404(id)
    
    # Add adjusted times (3 hours ahead) for display
    expense.created_at_adjusted = expense.created_at + timedelta(hours=3)
    expense.updated_at_adjusted = expense.updated_at + timedelta(hours=3)
    
    return render_template('expense_details.html', expense=expense)

# Supplier Management Routes
@app.route('/suppliers')
@login_required
@role_required(['admin'])
def suppliers():
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Search and filter parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        
        # Build query
        query = Supplier.query
        
        if search:
            query = query.filter(
                or_(
                    Supplier.name.ilike(f'%{search}%'),
                    Supplier.contact_person.ilike(f'%{search}%'),
                    Supplier.email.ilike(f'%{search}%'),
                    Supplier.phone.ilike(f'%{search}%')
                )
            )
        
        if status == 'active':
            query = query.filter(Supplier.is_active == True)
        elif status == 'inactive':
            query = query.filter(Supplier.is_active == False)
        
        # Pagination
        suppliers = query.order_by(Supplier.name).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('suppliers.html', suppliers=suppliers, search=search, status=status)
    except Exception as e:
        print(f"Error in suppliers route: {e}")
        flash('An error occurred while loading suppliers.', 'error')
        return redirect(url_for('index'))

@app.route('/add_supplier', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_supplier():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            contact_person = request.form.get('contact_person')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')
            tax_number = request.form.get('tax_number')
            payment_terms = request.form.get('payment_terms')
            credit_limit = request.form.get('credit_limit')
            notes = request.form.get('notes')
            is_active = request.form.get('is_active') == 'on'
            
            if not name:
                flash('Supplier name is required', 'error')
                return redirect(url_for('add_supplier'))
            
            # Convert credit_limit to decimal if provided
            credit_limit_decimal = None
            if credit_limit:
                try:
                    credit_limit_decimal = float(credit_limit)
                except ValueError:
                    flash('Invalid credit limit amount', 'error')
                    return redirect(url_for('add_supplier'))
            
            new_supplier = Supplier(
                name=name,
                contact_person=contact_person,
                email=email,
                phone=phone,
                address=address,
                tax_number=tax_number,
                payment_terms=payment_terms,
                credit_limit=credit_limit_decimal,
                notes=notes,
                is_active=is_active
            )
            
            db.session.add(new_supplier)
            db.session.commit()
            
            flash('Supplier added successfully', 'success')
            return redirect(url_for('suppliers'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding supplier: {e}")
            flash('An error occurred while adding supplier.', 'error')
            return redirect(url_for('add_supplier'))
    
    return render_template('add_supplier.html')

@app.route('/edit_supplier/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            contact_person = request.form.get('contact_person')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')
            tax_number = request.form.get('tax_number')
            payment_terms = request.form.get('payment_terms')
            credit_limit = request.form.get('credit_limit')
            notes = request.form.get('notes')
            is_active = request.form.get('is_active') == 'on'
            
            if not name:
                flash('Supplier name is required', 'error')
                return redirect(url_for('edit_supplier', id=id))
            
            # Convert credit_limit to decimal if provided
            credit_limit_decimal = None
            if credit_limit:
                try:
                    credit_limit_decimal = float(credit_limit)
                except ValueError:
                    flash('Invalid credit limit amount', 'error')
                    return redirect(url_for('edit_supplier', id=id))
            
            supplier.name = name
            supplier.contact_person = contact_person
            supplier.email = email
            supplier.phone = phone
            supplier.address = address
            supplier.tax_number = tax_number
            supplier.payment_terms = payment_terms
            supplier.credit_limit = credit_limit_decimal
            supplier.notes = notes
            supplier.is_active = is_active
            
            db.session.commit()
            flash('Supplier updated successfully', 'success')
            return redirect(url_for('suppliers'))
        except Exception as e:
            db.session.rollback()
            print(f"Error updating supplier: {e}")
            flash('An error occurred while updating supplier.', 'error')
            return redirect(url_for('edit_supplier', id=id))
    
    return render_template('edit_supplier.html', supplier=supplier)

@app.route('/delete_supplier/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_supplier(id):
    try:
        supplier = Supplier.query.get_or_404(id)
        
        # Check if supplier has purchase orders
        if supplier.purchase_orders:
            flash('Cannot delete supplier with associated purchase orders', 'error')
            return redirect(url_for('suppliers'))
        
        db.session.delete(supplier)
        db.session.commit()
        flash('Supplier deleted successfully', 'success')
        return redirect(url_for('suppliers'))
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting supplier: {e}")
        flash('An error occurred while deleting supplier.', 'error')
        return redirect(url_for('suppliers'))

# Purchase Order Routes
@app.route('/purchase_orders')
@login_required
@role_required(['admin'])
def purchase_orders():
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Search and filter parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        supplier_id = request.args.get('supplier_id', '')
        branch_id = request.args.get('branch_id', '')
        
        # Build query
        query = PurchaseOrder.query.select_from(PurchaseOrder).join(
            Supplier, PurchaseOrder.supplier_id == Supplier.id
        ).join(
            Branch, PurchaseOrder.branch_id == Branch.id
        ).join(
            User, PurchaseOrder.user_id == User.id
        )
        
        if search:
            query = query.filter(
                or_(
                    PurchaseOrder.po_number.ilike(f'%{search}%'),
                    Supplier.name.ilike(f'%{search}%'),
                    User.firstname.ilike(f'%{search}%'),
                    User.lastname.ilike(f'%{search}%')
                )
            )
        
        if status:
            query = query.filter(PurchaseOrder.status == status)
        
        if supplier_id:
            query = query.filter(PurchaseOrder.supplier_id == supplier_id)
        
        if branch_id:
            query = query.filter(PurchaseOrder.branch_id == branch_id)
        
        # Pagination
        purchase_orders = query.order_by(PurchaseOrder.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get suppliers and branches for filters
        suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
        branches = Branch.query.all()
        
        return render_template('purchase_orders.html', 
                             purchase_orders=purchase_orders, 
                             suppliers=suppliers,
                             branches=branches,
                             search=search, 
                             status=status,
                             supplier_id=supplier_id,
                             branch_id=branch_id)
    except Exception as e:
        print(f"Error in purchase_orders route: {e}")
        flash('An error occurred while loading purchase orders.', 'error')
        return redirect(url_for('index'))

@app.route('/add_purchase_order', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_purchase_order():
    if request.method == 'POST':
        try:
            supplier_id = request.form.get('supplier_id')
            branch_id = request.form.get('branch_id')
            order_date = request.form.get('order_date')
            expected_delivery_date = request.form.get('expected_delivery_date')
            notes = request.form.get('notes')
            
            if not supplier_id or not branch_id or not order_date:
                flash('Supplier, Branch, and Order Date are required', 'error')
                return redirect(url_for('add_purchase_order'))
            
            # Generate PO number
            today = datetime.now(EAT)
            po_number = f"PO-{today.strftime('%Y%m%d')}-{today.strftime('%H%M%S')}"
            
            new_po = PurchaseOrder(
                po_number=po_number,
                supplier_id=supplier_id,
                branch_id=branch_id,
                user_id=current_user.id,
                order_date=datetime.strptime(order_date, '%Y-%m-%d').date(),
                expected_delivery_date=datetime.strptime(expected_delivery_date, '%Y-%m-%d').date() if expected_delivery_date else None,
                notes=notes
            )
            
            db.session.add(new_po)
            db.session.commit()
            
            # Process purchase order items
            items_data = request.form.getlist('items_data')
            if items_data:
                for item_data in items_data:
                    if item_data.strip():
                        # Parse item data (format: product_code|product_name|quantity|unit)
                        parts = item_data.split('|')
                        if len(parts) >= 3:
                            product_code = parts[0].strip()
                            product_name = parts[1].strip() if len(parts) > 1 else ''
                            quantity = float(parts[2].strip()) if parts[2].strip().replace('.', '').isdigit() else 1
                            unit = parts[3].strip() if len(parts) > 3 else 'pieces'
                            
                            po_item = PurchaseOrderItem(
                                purchase_order_id=new_po.id,
                                product_code=product_code,
                                product_name=product_name,
                                quantity=quantity,
                                unit=unit
                            )
                            db.session.add(po_item)
                
                db.session.commit()
            
            flash('Purchase Order created successfully with items', 'success')
            return redirect(url_for('edit_purchase_order', id=new_po.id))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating purchase order: {e}")
            flash('An error occurred while creating purchase order.', 'error')
            return redirect(url_for('add_purchase_order'))
    
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    branches = Branch.query.all()
    products = ProductCatalog.query.order_by(ProductCatalog.name).all()
    
    return render_template('add_purchase_order.html', 
                         suppliers=suppliers, 
                         branches=branches,
                         products=products)

@app.route('/edit_purchase_order/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_purchase_order(id):
    try:
        print(f"🔍 Attempting to access edit_purchase_order for ID: {id}")
        print(f"🔍 Current user: {current_user.email if current_user.is_authenticated else 'Not authenticated'}")
        print(f"🔍 User role: {current_user.role if current_user.is_authenticated else 'No role'}")
        
        # Check if purchase order exists
        po = PurchaseOrder.query.get(id)
        if not po:
            print(f"❌ Purchase Order with ID {id} not found in database")
            flash(f'Purchase Order with ID {id} not found.', 'error')
            return redirect(url_for('purchase_orders'))
        
        print(f"✅ Found Purchase Order: {po.po_number} (ID: {po.id})")
        print(f"✅ PO Status: {po.status}")
        print(f"✅ PO Supplier ID: {po.supplier_id}")
        print(f"✅ PO Branch ID: {po.branch_id}")
        
        if request.method == 'POST':
            try:
                print(f"📝 Processing POST request for PO {id}")
                supplier_id = request.form.get('supplier_id')
                branch_id = request.form.get('branch_id')
                order_date = request.form.get('order_date')
                expected_delivery_date = request.form.get('expected_delivery_date')
                notes = request.form.get('notes')
                status = request.form.get('status')
                
                print(f"📝 Form data received:")
                print(f"   - supplier_id: {supplier_id}")
                print(f"   - branch_id: {branch_id}")
                print(f"   - order_date: {order_date}")
                print(f"   - expected_delivery_date: {expected_delivery_date}")
                print(f"   - status: {status}")
                
                if not supplier_id or not branch_id or not order_date:
                    print(f"❌ Missing required fields")
                    flash('Supplier, Branch, and Order Date are required', 'error')
                    return redirect(url_for('edit_purchase_order', id=id))
                
                po.supplier_id = supplier_id
                po.branch_id = branch_id
                po.order_date = datetime.strptime(order_date, '%Y-%m-%d').date()
                po.expected_delivery_date = datetime.strptime(expected_delivery_date, '%Y-%m-%d').date() if expected_delivery_date else None
                po.notes = notes
                
                if status and status != po.status:
                    po.status = status
                    if status == 'approved':
                        po.approved_by = current_user.id
                        po.approved_at = datetime.now(EAT)
                
                db.session.commit()
                print(f"✅ Purchase Order updated successfully")
                flash('Purchase Order updated successfully', 'success')
                return redirect(url_for('purchase_orders'))
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error updating purchase order: {str(e)}")
                print(f"❌ Error type: {type(e).__name__}")
                import traceback
                print(f"❌ Full traceback:")
                traceback.print_exc()
                flash(f'An error occurred while updating purchase order: {str(e)}', 'error')
                return redirect(url_for('edit_purchase_order', id=id))
        
        # GET request - prepare data for template
        try:
            print(f"📋 Preparing data for template")
            suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
            branches = Branch.query.all()
            products = ProductCatalog.query.all()
            
            print(f"✅ Data prepared:")
            print(f"   - Suppliers count: {len(suppliers)}")
            print(f"   - Branches count: {len(branches)}")
            print(f"   - ProductCatalogs count: {len(products)}")
            
            # Check if template exists
            import os
            template_path = os.path.join(app.template_folder, 'edit_purchase_order.html')
            if os.path.exists(template_path):
                print(f"✅ Template file exists: {template_path}")
            else:
                print(f"❌ Template file not found: {template_path}")
            
            print(f"🎯 Attempting to render template...")
            
            # Debug: Print PO data structure
            print(f"🔍 PO data structure:")
            print(f"   - ID: {po.id}")
            print(f"   - PO Number: {po.po_number}")
            print(f"   - Status: {po.status}")
            print(f"   - Items count: {len(po.items) if po.items else 0}")
            
            if po.items:
                for i, item in enumerate(po.items):
                    print(f"   - Item {i+1}:")
                    print(f"     * ID: {item.id}")
                    print(f"     * ProductCatalog Name: {item.product_name}")
                    print(f"     * ProductCatalog Code: {item.product_code}")
                    print(f"     * Quantity: {item.quantity}")
                    print(f"     * Unit Price: {item.unit_price}")
                    print(f"     * Total Price: {item.total_price}")
                    print(f"     * Received Quantity: {item.received_quantity}")
            
            result = render_template('edit_purchase_order.html', 
                                   po=po, 
                                   suppliers=suppliers, 
                                   branches=branches,
                                   products=products)
            print(f"✅ Template rendered successfully")
            return result
            
        except Exception as e:
            print(f"❌ Error preparing template data: {str(e)}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            print(f"❌ Full traceback:")
            traceback.print_exc()
            flash(f'An error occurred while loading the page: {str(e)}', 'error')
            return redirect(url_for('purchase_orders'))
            
    except Exception as e:
        print(f"❌ Critical error in edit_purchase_order route: {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Full traceback:")
        traceback.print_exc()
        flash(f'A critical error occurred: {str(e)}', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/test_db_connection')
def test_db_connection():
    """Test route to check database connection and models"""
    try:
        print("🔍 Testing database connection...")
        
        # Test basic database connection
        db.session.execute('SELECT 1')
        print("✅ Database connection successful")
        
        # Test PurchaseOrder model
        po_count = PurchaseOrder.query.count()
        print(f"✅ PurchaseOrder model working. Total POs: {po_count}")
        
        # Test Supplier model
        supplier_count = Supplier.query.count()
        print(f"✅ Supplier model working. Total suppliers: {supplier_count}")
        
        # Test Branch model
        branch_count = Branch.query.count()
        print(f"✅ Branch model working. Total branches: {branch_count}")
        
        # Test ProductCatalog model
        product_count = ProductCatalog.query.count()
        print(f"✅ ProductCatalog model working. Total products: {product_count}")
        
        # Check if PO with ID 1 exists
        po_1 = PurchaseOrder.query.get(1)
        if po_1:
            print(f"✅ Purchase Order ID 1 exists: {po_1.po_number}")
            print(f"   - Status: {po_1.status}")
            print(f"   - Supplier ID: {po_1.supplier_id}")
            print(f"   - Branch ID: {po_1.branch_id}")
        else:
            print("❌ Purchase Order ID 1 does not exist")
        
        return jsonify({
            'status': 'success',
            'message': 'Database connection and models working',
            'po_count': po_count,
            'supplier_count': supplier_count,
            'branch_count': branch_count,
            'product_count': product_count,
            'po_1_exists': po_1 is not None
        })
        
    except Exception as e:
        print(f"❌ Database test failed: {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Full traceback:")
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e),
            'error_type': type(e).__name__
        }), 500

@app.route('/delete_purchase_order/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_purchase_order(id):
    try:
        po = PurchaseOrder.query.get_or_404(id)
        
        if po.status not in ['draft', 'cancelled']:
            flash('Cannot delete purchase order that is not in draft or cancelled status', 'error')
            return redirect(url_for('purchase_orders'))
        
        db.session.delete(po)
        db.session.commit()
        flash('Purchase Order deleted successfully', 'success')
        return redirect(url_for('purchase_orders'))
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting purchase order: {e}")
        flash('An error occurred while deleting purchase order.', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/add_po_item/<int:po_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def add_po_item(po_id):
    try:
        po = PurchaseOrder.query.get_or_404(po_id)
        
        if po.status not in ['draft', 'submitted']:
            flash('Cannot add items to purchase order that is not in draft or submitted status', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        product_code = request.form.get('product_code')
        product_name = request.form.get('product_name')
        quantity = request.form.get('quantity')
        unit_price = request.form.get('unit_price')
        notes = request.form.get('notes')
        
        # At least one of product name or product code must be provided, plus quantity
        if (not product_code and not product_name) or not quantity:
            flash('Either product name or product code (or both) and quantity are required', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        try:
            quantity = Decimal(str(quantity)) if quantity else None
            if quantity is not None and quantity <= 0:
                raise ValueError("Quantity must be positive")
            unit_price = Decimal(str(unit_price)) if unit_price else None
            total_price = quantity * unit_price if unit_price and quantity else None
        except (ValueError, TypeError):
            flash('Invalid quantity or unit price', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        new_item = PurchaseOrderItem(
            purchase_order_id=po_id,
            product_code=product_code,
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            notes=notes
        )
        
        db.session.add(new_item)
        
        # Update PO totals
        po.subtotal = sum(item.total_price for item in po.items if item.total_price)
        po.total_amount = po.subtotal + (po.tax_amount or Decimal('0')) - (po.discount_amount or Decimal('0'))
        
        db.session.commit()
        flash('Item added to purchase order successfully', 'success')
        return redirect(url_for('edit_purchase_order', id=po_id))
    except Exception as e:
        db.session.rollback()
        print(f"Error adding PO item: {e}")
        flash('An error occurred while adding item to purchase order.', 'error')
        return redirect(url_for('edit_purchase_order', id=po_id))

@app.route('/edit_po_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_po_item(item_id):
    try:
        print(f"🔍 Attempting to edit PO item with ID: {item_id}")
        
        # Get the PO item
        po_item = PurchaseOrderItem.query.get_or_404(item_id)
        print(f"✅ Found PO Item: {po_item.product_name} (ID: {po_item.id})")
        
        # Get the parent purchase order
        po = po_item.purchase_order
        print(f"✅ Parent PO: {po.po_number} (ID: {po.id})")
        
        if request.method == 'POST':
            try:
                print(f"📝 Processing POST request for PO item {item_id}")
                
                # Get form data
                product_code = request.form.get('product_code', '').strip()
                product_name = request.form.get('product_name', '').strip()
                quantity = request.form.get('quantity')
                unit = request.form.get('unit', 'pieces')
                unit_price = request.form.get('unit_price')
                
                print(f"📝 Form data received:")
                print(f"   - product_code: {product_code}")
                print(f"   - product_name: {product_name}")
                print(f"   - quantity: {quantity}")
                print(f"   - unit: {unit}")
                print(f"   - unit_price: {unit_price}")
                
                # At least one of product name or product code must be provided, plus quantity
                if (not product_code and not product_name) or not quantity:
                    print(f"❌ Missing required fields")
                    flash('Either product name or product code (or both) and quantity are required', 'error')
                    return redirect(url_for('edit_po_item', item_id=item_id))
                
                # Validate numeric fields
                try:
                    quantity = Decimal(str(quantity)) if quantity else None
                    if quantity is not None and quantity <= 0:
                        raise ValueError("Quantity must be positive")
                    unit_price = Decimal(str(unit_price)) if unit_price else None
                except (ValueError, TypeError):
                    print(f"❌ Invalid quantity or unit price")
                    flash('Invalid quantity or unit price', 'error')
                    return redirect(url_for('edit_po_item', item_id=item_id))
                
                # Check if PO is editable
                if po.status not in ['draft', 'submitted']:
                    print(f"❌ PO status '{po.status}' does not allow editing")
                    flash('Cannot edit items in purchase order that is not in draft or submitted status', 'error')
                    return redirect(url_for('edit_purchase_order', id=po.id))
                
                # Update the item
                po_item.product_code = product_code
                po_item.product_name = product_name
                po_item.quantity = quantity
                po_item.unit = unit
                po_item.unit_price = unit_price
                
                # Calculate total price if unit price is provided
                if unit_price:
                    po_item.total_price = quantity * unit_price
                else:
                    po_item.total_price = None
                
                po_item.updated_at = datetime.now(EAT)
                
                # Update PO totals
                po.subtotal = sum(item.total_price for item in po.items if item.total_price)
                po.total_amount = po.subtotal + (po.tax_amount or Decimal('0')) - (po.discount_amount or Decimal('0'))
                
                db.session.commit()
                print(f"✅ PO Item updated successfully")
                print(f"✅ PO totals updated - Subtotal: {po.subtotal}, Total: {po.total_amount}")
                flash('Purchase Order Item updated successfully', 'success')
                return redirect(url_for('edit_purchase_order', id=po.id))
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error updating PO item: {str(e)}")
                print(f"❌ Error type: {type(e).__name__}")
                import traceback
                print(f"❌ Full traceback:")
                traceback.print_exc()
                flash(f'An error occurred while updating the item: {str(e)}', 'error')
                return redirect(url_for('edit_po_item', item_id=item_id))
        
        # GET request - show edit form
        return render_template('edit_po_item.html', po_item=po_item, po=po)
        
    except Exception as e:
        print(f"❌ Critical error in edit_po_item route: {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Full traceback:")
        traceback.print_exc()
        flash(f'A critical error occurred: {str(e)}', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/delete_po_item/<int:item_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_po_item(item_id):
    try:
        item = PurchaseOrderItem.query.get_or_404(item_id)
        po = item.purchase_order
        
        if po.status not in ['draft', 'submitted']:
            flash('Cannot delete items from purchase order that is not in draft or submitted status', 'error')
            return redirect(url_for('edit_purchase_order', id=po.id))
        
        db.session.delete(item)
        
        # Update PO totals
        po.subtotal = sum(item.total_price for item in po.items if item.total_price)
        po.total_amount = po.subtotal + (po.tax_amount or Decimal('0')) - (po.discount_amount or Decimal('0'))
        
        db.session.commit()
        flash('Item removed from purchase order successfully', 'success')
        return redirect(url_for('edit_purchase_order', id=po.id))
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting PO item: {e}")
        flash('An error occurred while removing item from purchase order.', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/receive_po/<int:po_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def receive_po(po_id):
    try:
        po = PurchaseOrder.query.get_or_404(po_id)
        
        if po.status != 'ordered':
            flash('Purchase order must be in ordered status to receive', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        # Update received quantities
        for item in po.items:
            received_qty = request.form.get(f'received_qty_{item.id}', 0)
            try:
                received_qty = int(received_qty)
                if received_qty > 0:
                    item.received_quantity = received_qty
            except ValueError:
                flash('Invalid received quantity', 'error')
                return redirect(url_for('edit_purchase_order', id=po_id))
        
        po.status = 'received'
        po.delivery_date = datetime.now(EAT).date()
        
        db.session.commit()
        flash('Purchase order received successfully', 'success')
        return redirect(url_for('purchase_order_details', po_id=po_id))
    except Exception as e:
        db.session.rollback()
        print(f"Error receiving PO: {e}")
        flash('An error occurred while receiving purchase order.', 'error')
        return redirect(url_for('purchase_order_details', po_id=po_id))

@app.route('/purchase_order_details/<int:po_id>')
@login_required
@role_required(['admin'])
def purchase_order_details(po_id):
    try:
                
        po = PurchaseOrder.query.get(po_id)
        if not po:
            
            flash(f'Purchase Order with ID {po_id} not found', 'error')
            return redirect(url_for('purchase_orders'))
        
        # Add adjusted times (3 hours ahead) for display
        if po.created_at:
            po.created_at_adjusted = po.created_at + timedelta(hours=3)
        if po.approved_at:
            po.approved_at_adjusted = po.approved_at + timedelta(hours=3)
        
        return render_template('purchase_order_details.html', po=po)
        
    except Exception as e:
        
        import traceback
       
        traceback.print_exc()
        flash(f'A critical error occurred while loading purchase order details: {str(e)}', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/export_purchase_order_pdf/<int:po_id>')
@login_required
@role_required(['admin'])
def export_purchase_order_pdf(po_id):
    try:
        # Get the purchase order
        po = PurchaseOrder.query.get_or_404(po_id)
        
        # Create PDF buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#2c3e50')
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            textColor=colors.HexColor('#34495e')
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=12
        )
        
        # Load the logo image
        try:
            logo_path = os.path.join(app.static_folder, 'assets', 'img', 'logo.png')
            print(f"Loading logo from: {logo_path}")
            logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
            logo_cell = logo_image
        except Exception as e:
            print(f"Error loading logo: {e}")
            # Create a placeholder if logo fails to load
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=18 color="#1a365d">ABZ HARDWARE LIMITED</font></b>
            </para>
            ''', normal_style)
        
        # Create the letterhead table for proper layout
        letterhead_data = [[
            # Left side - Logo Image
            logo_cell,
            
            # Right side - Contact Information
            Paragraph('''
            <para align=right>
            <b><font size=11 color="#1a365d">Kombo Munyiri Road,</font></b><br/>
            <b><font size=11 color="#1a365d">Gikomba, Nairobi, Kenya</font></b><br/>
            <font size=9 color="#666666">0711 732 341 or 0725 000 055</font><br/>
            <font size=9 color="#666666">info@abzhardware.co.ke</font><br/>
            <font size=9 color="#666666">www.abzhardware.co.ke</font>
            </para>
            ''', normal_style)
        ]]
        
        # Create letterhead table
        letterhead_table = Table(letterhead_data, colWidths=[3.5*inch, 3.5*inch])
        letterhead_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ]))
        
        elements.append(letterhead_table)
        elements.append(Spacer(1, 10))
        
        # Add the colored line separator (yellow and dark blue)
        separator_data = [[""]]
        separator_table = Table(separator_data, colWidths=[7*inch], rowHeights=[0.05*inch])
        separator_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4b942')),  # Yellow color
        ]))
        
        elements.append(separator_table)
        elements.append(Spacer(1, 30))
        
        # Purchase Order Title
        elements.append(Paragraph(f"PURCHASE ORDER", title_style))
        elements.append(Spacer(1, 30))
        
        # PO Details Section
        po_details = f"""
        <b>PO Number:</b> {po.po_number}<br/>
        <b>Date:</b> {po.order_date.strftime('%B %d, %Y') if po.order_date else 'N/A'}<br/>
        <b>Supplier:</b> {po.supplier.name if po.supplier else 'N/A'}<br/>
        <b>Branch:</b> {po.branch.name if po.branch else 'N/A'}"""
        
        # Only add delivery date if it exists
        if po.expected_delivery_date:
            po_details += f"<br/><b>Expected Delivery:</b> {po.expected_delivery_date.strftime('%B %d, %Y')}"
        
        po_details += ""
        elements.append(Paragraph(po_details, normal_style))
        elements.append(Spacer(1, 30))
        
        # Items Table
        if po.items:
            elements.append(Paragraph("ITEMS ORDERED", heading_style))
            
            # Table data - Product (Name - Code), Quantity
            data = [['Product', 'Quantity']]
            
            # Create a style for product names that allows wrapping
            product_name_style = ParagraphStyle(
                'ProductCatalogName',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=0,
                spaceBefore=0,
                leading=13,  # Line spacing for multi-line text
                alignment=0,  # Left alignment
                fontName='Helvetica'
            )
            
            for item in po.items:
                # Format quantity using the same logic as the template filter
                if item.quantity is None:
                    formatted_quantity = '0'
                else:
                    try:
                        float_val = float(item.quantity)
                        if float_val == int(float_val):
                            formatted_quantity = str(int(float_val))
                        else:
                            formatted_quantity = f"{float_val:g}"
                    except (ValueError, TypeError):
                        formatted_quantity = str(item.quantity)
                
                # Format product name and code combined
                product_name = item.product_name or ''
                product_code = item.product_code or ''
                unit = item.unit
                
                # Combine product name and code
                if product_name and product_code:
                    product_display = f"{product_name} - {product_code}"
                elif product_name:
                    product_display = product_name
                elif product_code:
                    product_display = product_code
                else:
                    product_display = 'N/A'
                
                # Combine quantity and unit (show unit only if it's explicitly set and not null)
                if unit and unit.strip():
                    quantity_unit_display = f"{formatted_quantity} {unit.upper()}"
                else:
                    quantity_unit_display = formatted_quantity
                
                data.append([
                    Paragraph(product_display.upper(), product_name_style),
                    quantity_unit_display
                ])
            
            # Create table with 2 columns
            table = Table(data, colWidths=[5*inch, 2*inch])
            table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                
                # Data rows
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#4a5568')),
                
                # Alternating row colors
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
                
                # Alignment adjustments
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Product (Name - Code) left
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Quantity center
                
                # Padding
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 30))
        else:
            elements.append(Paragraph("No items in this purchase order.", normal_style))
            elements.append(Spacer(1, 30))
        
        # Total Amount
        if po.total_amount:
            total_data = [['Total Amount:', f"KSh {po.total_amount:,.2f}"]]
            
            total_table = Table(total_data, colWidths=[2*inch, 2*inch])
            total_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#4a5568')),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e2e8f0')),
            ]))
            
            elements.append(total_table)
            elements.append(Spacer(1, 30))
        
        # Notes section
        if po.notes:
            elements.append(Paragraph("NOTES", heading_style))
            elements.append(Paragraph(po.notes, normal_style))
            elements.append(Spacer(1, 20))
        
        # Footer
        footer_text = f"""
        <para align=center>
        <font size=8 color="#95a5a6">
        Generated on {datetime.now(EAT).strftime('%B %d, %Y at %I:%M %p')} by {po.user.firstname} {po.user.lastname}<br/>
        This is a computer-generated document and does not require a signature.
        </font>
        </para>
        """
        elements.append(Spacer(1, 50))
        elements.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Create response
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=purchase_order_{po.po_number}.pdf'
        
        return response
        
    except Exception as e:
        print(f"Error generating purchase order PDF: {e}")
        flash('An error occurred while generating the PDF.', 'error')
        return redirect(url_for('purchase_orders'))

@app.route('/add_purchase_order_item/<int:po_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def add_purchase_order_item(po_id):
    try:
        po = PurchaseOrder.query.get_or_404(po_id)
        
        # Check if PO is in editable state
        if po.status not in ['draft', 'submitted']:
            flash('Cannot add items to a purchase order that is not in draft or submitted status', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        product_code = request.form.get('product_code', '').strip()
        product_name = request.form.get('product_name', '').strip()
        quantity = request.form.get('quantity')
        notes = request.form.get('notes', '')
        
        # At least one of product name or product code must be provided, plus quantity
        if (not product_code and not product_name) or not quantity:
            flash('Either product name or product code (or both) and quantity are required', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
        except ValueError:
            flash('Quantity must be a positive number', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        # Create new purchase order item
        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_code=product_code,
            product_name=product_name,
            quantity=quantity,
            notes=notes
        )
        
        db.session.add(po_item)
        db.session.commit()
        
        flash('Item added successfully to purchase order', 'success')
        return redirect(url_for('edit_purchase_order', id=po_id))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding item to purchase order: {e}")
        flash('An error occurred while adding item to purchase order', 'error')
        return redirect(url_for('edit_purchase_order', id=po_id))

@app.route('/delete_purchase_order_item/<int:item_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_purchase_order_item(item_id):
    try:
        po_item = PurchaseOrderItem.query.get_or_404(item_id)
        po = po_item.purchase_order
        
        # Check if PO is in editable state
        if po.status not in ['draft', 'submitted']:
            flash('Cannot delete items from a purchase order that is not in draft or submitted status', 'error')
            return redirect(url_for('edit_purchase_order', id=po.id))
        
        db.session.delete(po_item)
        db.session.commit()
        
        flash('Item removed successfully from purchase order', 'success')
        return redirect(url_for('edit_purchase_order', id=po.id))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting purchase order item: {e}")
        flash('An error occurred while deleting item from purchase order', 'error')
        return redirect(url_for('edit_purchase_order', id=po.id))

# Error handlers
@app.errorhandler(IntegrityError)
def handle_integrity_error(error):
    db.session.rollback()
    print(f"Integrity error: {error}")
    flash('Cannot perform this action. The record has associated data that prevents deletion.', 'error')
    # Only redirect if we have a valid referrer and it's not the same page
    if request.referrer and request.referrer != request.url:
        return redirect(request.referrer)
    # Fallback to login if no valid referrer
    return redirect(url_for('login'))

@app.errorhandler(Exception)
def handle_general_error(error):
    db.session.rollback()
    print(f"General error: {error}")
    flash('An unexpected error occurred. Please try again.', 'error')
    # Only redirect if we have a valid referrer and it's not the same page
    if request.referrer and request.referrer != request.url:
        return redirect(request.referrer)
    # Fallback to login if no valid referrer
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long', 'error')
            return redirect(url_for('change_password'))
        
        # Verify current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('change_password'))
        
        # Update password
        try:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while changing password', 'error')
            return redirect(url_for('change_password'))
    
    return render_template('change_password.html')

# Sales Report Route - Matching abz-cashier-portal structure
@app.route('/sales_report')
@login_required
@role_required(['admin'])
def sales_report():
    from datetime import datetime, timedelta
    
    # Get date range and branch filter from query parameters
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    branch_id = request.args.get('branch_id', type=int)
    
    # Convert to datetime objects
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # Get sales data
    sales_data_query = db.session.query(
        func.date(Payment.created_at).label('date'),
        func.count(Payment.id).label('payment_count'),
        func.sum(Payment.amount).label('total_amount')
    ).join(Order, Payment.orderid == Order.id).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt
    )
    
    # Apply branch filter if specified
    if branch_id:
        sales_data_query = sales_data_query.filter(Order.branchid == branch_id)
    
    sales_data = sales_data_query.group_by(func.date(Payment.created_at)).order_by(func.date(Payment.created_at)).all()
    
    # Get daily profit data separately to avoid join conflicts
    daily_profits_query = db.session.query(
        func.date(Payment.created_at).label('date'),
        func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity).label('daily_profit')
    ).select_from(Payment).join(Order, Payment.orderid == Order.id).join(
        OrderItem, Order.id == OrderItem.orderid
    ).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt,
        OrderItem.final_price.isnot(None),
        OrderItem.buying_price.isnot(None)
    )
    
    # Apply branch filter if specified
    if branch_id:
        daily_profits_query = daily_profits_query.filter(Order.branchid == branch_id)
    
    daily_profits = daily_profits_query.group_by(func.date(Payment.created_at)).all()
    
    # Create a dictionary for quick profit lookup
    profit_dict = {row.date: row.daily_profit for row in daily_profits}
    
    # Create enhanced sales data with profit information
    enhanced_sales_data = []
    for row in sales_data:
        enhanced_sales_data.append({
            'date': row.date,
            'payment_count': row.payment_count,
            'total_amount': row.total_amount,
            'total_profit': profit_dict.get(row.date, 0.0)
        })
    
    # Calculate totals
    total_revenue = sum(row.total_amount for row in sales_data if row.total_amount)
    total_payments = sum(row.payment_count for row in sales_data)
    
    # Calculate total profit
    total_profit_query = db.session.query(
        db.func.sum((OrderItem.final_price - OrderItem.buying_price) * OrderItem.quantity)
    ).join(Order, OrderItem.orderid == Order.id).join(
        Payment, Order.id == Payment.orderid
    ).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt,
        OrderItem.final_price.isnot(None),
        OrderItem.buying_price.isnot(None)
    )
    
    # Apply branch filter if specified
    if branch_id:
        total_profit_query = total_profit_query.filter(Order.branchid == branch_id)
    
    total_profit = total_profit_query.scalar() or 0.0
    
    # Get all branches for dropdown
    branches = Branch.query.all()
    
    # Get selected branch info
    selected_branch = None
    if branch_id:
        selected_branch = Branch.query.get(branch_id)
    
    return render_template('sales_report.html', 
                         sales_data=enhanced_sales_data,
                         start_date=start_date,
                         end_date=end_date,
                         total_revenue=total_revenue,
                         total_payments=total_payments,
                         total_profit=float(total_profit),
                         branches=branches,
                         selected_branch=selected_branch,
                         current_branch_id=branch_id)

@app.route('/sales_report/daily-details/<date>')
@login_required
@role_required(['admin'])
def daily_sales_details(date):
    """Show detailed breakdown of sales for a specific date"""
    try:
        # Convert date string to datetime
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        next_day = date_obj + timedelta(days=1)
        
        # Get payments for the specific date
        payments = db.session.query(Payment).join(Order).filter(
            Payment.payment_status == 'completed',
            Payment.created_at >= date_obj,
            Payment.created_at < next_day
        ).all()
        
        # Get order items for the specific date
        order_items = db.session.query(OrderItem).join(Order).filter(
            Order.created_at >= date_obj,
            Order.created_at < next_day,
            Order.payment_status.in_(['paid', 'partially_paid'])
        ).all()
        
        # Calculate totals
        total_revenue = sum(payment.amount for payment in payments)
        total_payments = len(payments)
        total_items = sum(item.quantity for item in order_items)
        
        return render_template('daily_sales_details.html',
                             date=date_obj,
                             payments=payments,
                             order_items=order_items,
                             total_revenue=total_revenue,
                             total_payments=total_payments,
                             total_items=total_items)
        
    except Exception as e:
        print(f"Error in daily sales details: {e}")
        flash('An error occurred while loading daily sales details.', 'error')
        return redirect(url_for('sales_report'))

@app.route('/delete_payment', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_payment():
    """Delete a payment from an order"""
    try:
        payment_id = request.form.get('payment_id', type=int)
        order_id = request.form.get('order_id', type=int)
        
        if not payment_id or not order_id:
            flash('Invalid payment or order ID.', 'error')
            return redirect(url_for('orders'))
        
        # Get the payment
        payment = Payment.query.get_or_404(payment_id)
        
        # Verify the payment belongs to the specified order
        if payment.orderid != order_id:
            flash('Payment does not belong to the specified order.', 'error')
            return redirect(url_for('order_details', order_id=order_id))
        
        # Delete the payment
        db.session.delete(payment)
        db.session.commit()
        
        flash(f'Payment #{payment_id} has been successfully deleted.', 'success')
        
    except Exception as e:
        print(f"Error deleting payment: {e}")
        db.session.rollback()
        flash('An error occurred while deleting the payment.', 'error')
    
    # Redirect back to the order details page
    return redirect(url_for('order_details', order_id=order_id))

@app.route('/edit_payment', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_payment():
    """Edit a payment in an order"""
    try:
        payment_id = request.form.get('payment_id', type=int)
        order_id = request.form.get('order_id', type=int)
        payment_method = request.form.get('payment_method')
        amount = request.form.get('amount', type=float)
        payment_status = request.form.get('payment_status')
        reference_number = request.form.get('reference_number', '').strip()
        
        if not payment_id or not order_id or not payment_method or not amount or not payment_status:
            flash('All required fields must be filled.', 'error')
            return redirect(url_for('order_details', order_id=order_id))
        
        if amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('order_details', order_id=order_id))
        
        # Get the payment
        payment = Payment.query.get_or_404(payment_id)
        
        # Verify the payment belongs to the specified order
        if payment.orderid != order_id:
            flash('Payment does not belong to the specified order.', 'error')
            return redirect(url_for('order_details', order_id=order_id))
        
        # Update the payment
        payment.payment_method = payment_method
        payment.amount = amount
        payment.payment_status = payment_status
        payment.reference_number = reference_number if reference_number else None
        payment.updated_at = datetime.now()
        
        db.session.commit()
        
        flash(f'Payment #{payment_id} has been successfully updated.', 'success')
        
    except Exception as e:
        print(f"Error editing payment: {e}")
        db.session.rollback()
        flash('An error occurred while updating the payment.', 'error')
    
    # Redirect back to the order details page
    return redirect(url_for('order_details', order_id=order_id))

def migrate_existing_passwords():
    """Migrate existing plain text passwords to hashed passwords"""
    try:
        users = User.query.all()
        migrated_count = 0
        
        for user in users:
            if not user.is_password_hashed():
                # Generate a temporary password and hash it
                temp_password = "ChangeMe123!"  # Default password for existing users
                user.set_password(temp_password)
                migrated_count += 1
        
        if migrated_count > 0:
            db.session.commit()
            print(f"✅ Migrated {migrated_count} users to hashed passwords")
            print("⚠️  IMPORTANT: All migrated users now have password: ChangeMe123!")
            print("⚠️  Please ask users to change their passwords on first login")
        else:
            print("✅ All passwords are already hashed")
            
    except Exception as e:
        print(f"❌ Error during password migration: {e}")
        db.session.rollback()

if __name__ == '__main__':
    # Uncomment the line below to migrate existing passwords
    # with app.app_context():
    #     migrate_existing_passwords()
    
    app.run(debug=True)