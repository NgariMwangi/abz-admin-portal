from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
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
from sqlalchemy import or_

from extensions import db

app = Flask(__name__)
app.config.from_object(Config)

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
login_manager.login_view = 'login_post'

# Import models after db is initialized
from models import Branch, Category, User, Product, OrderType, Order, OrderItem, StockTransaction, Payment, SubCategory, ProductDescription, Expense, Supplier, PurchaseOrder, PurchaseOrderItem

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
                return redirect(url_for('login_post', next=request.url))
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

@app.route("/")
@login_required
@role_required(['admin']) 
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login_post'))
    
    # Get real business data
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    
    # Current date in EAT timezone
    now = datetime.now(EAT)
    today = now.date()
    this_month = now.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    
    # Dashboard statistics
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_branches = Branch.query.count()
    
    # Recent orders (last 7 days)
    recent_orders = Order.query.filter(
        Order.created_at >= today - timedelta(days=7)
    ).count()
    
    # Pending orders
    pending_orders = Order.query.filter_by(approvalstatus=False).count()
    
    # Total revenue (from approved orders)
    total_revenue = db.session.query(func.sum(OrderItem.final_price * OrderItem.quantity)).join(
        Order, OrderItem.orderid == Order.id
    ).filter(Order.approvalstatus == True).scalar() or 0
    
    # Monthly revenue
    monthly_revenue = db.session.query(func.sum(OrderItem.final_price * OrderItem.quantity)).join(
        Order, OrderItem.orderid == Order.id
    ).filter(
        and_(Order.approvalstatus == True, Order.created_at >= this_month)
    ).scalar() or 0
    
    # Low stock products (less than 10 items)
    low_stock_products = Product.query.filter(Product.stock < 10).count()
    
    # Recent activities
    recent_orders_list = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Branch statistics
    branch_stats = []
    for branch in Branch.query.all():
        branch_products = Product.query.filter_by(branchid=branch.id).count()
        branch_orders = Order.query.filter_by(branchid=branch.id).count()
        branch_stats.append({
            'branch': branch,
            'products': branch_products,
            'orders': branch_orders
        })
    
    # Top selling products
    top_products = db.session.query(
        Product, func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem, Product.id == OrderItem.productid).join(
        Order, OrderItem.orderid == Order.id
    ).filter(Order.approvalstatus == True).group_by(Product.id).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()
    
    # Expense statistics
    total_expenses = Expense.query.count()
    pending_expenses = Expense.query.filter_by(status='pending').count()
    approved_expenses = Expense.query.filter_by(status='approved').count()
    total_expense_amount = db.session.query(func.sum(Expense.amount)).filter_by(status='approved').scalar() or 0
    monthly_expenses = db.session.query(func.sum(Expense.amount)).filter(
        and_(Expense.status == 'approved', Expense.expense_date >= this_month)
    ).scalar() or 0
    
    return render_template("index.html", 
                         total_users=total_users,
                         total_products=total_products,
                         total_orders=total_orders,
                         total_branches=total_branches,
                         recent_orders=recent_orders,
                         pending_orders=pending_orders,
                         total_revenue=total_revenue,
                         monthly_revenue=monthly_revenue,
                         low_stock_products=low_stock_products,
                         recent_orders_list=recent_orders_list,
                         recent_users=recent_users,
                         branch_stats=branch_stats,
                         top_products=top_products,
                         total_expenses=total_expenses,
                         pending_expenses=pending_expenses,
                         approved_expenses=approved_expenses,
                         total_expense_amount=total_expense_amount,
                         monthly_expenses=monthly_expenses)

@app.route("/login", methods=["GET", "POST"])
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        print(email)
        print(password)
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            # Password is correct
            pass
        else:
            user = None
        print(user)
        # Check if user exists and password is correct
        if not user:
            print("User not found")
            flash('Please check your login details and try again.', 'danger')
            return redirect(url_for('login_post'))
            
        # If the above check passes, log the user in
        login_user(user)
        
        # Redirect to the page the user was trying to access or home
        next_page = request.args.get('next')
        return redirect(next_page or url_for('index'))
    
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
        
        # Create new admin user with hashed password
        new_user = User(
            email=email,
            firstname=firstname,
            lastname=lastname,
            password='',  # Will be set securely below
            role='admin',
            phone=phone
        )
        new_user.set_password(password)  # Hash the password securely
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Admin user registered successfully! You can now login.', 'success')
            return redirect(url_for('login_post'))
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
    return redirect(url_for('login_post'))

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

# Context processor to make branches available to all templates
@app.context_processor
def inject_branches():
    branches = Branch.query.all()
    return dict(branches=branches)

# Categories Routes
@app.route('/products')
@login_required
@role_required(['admin'])
def products():
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    branches = Branch.query.all()
    
    # Get selected branch from query parameter
    selected_branch_id = request.args.get('branch_id', type=int)
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)  # Default 10 items per page
    
    # Base query - don't join with Category since Product doesn't have direct relationship
    if selected_branch_id:
        # Filter products by selected branch
        base_query = Product.query.filter(Product.branchid == selected_branch_id)
    else:
        # Show all products if no branch is selected
        base_query = Product.query
    
    # Apply pagination
    pagination = base_query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    products = pagination.items
    
    return render_template('products.html', 
                         categories=categories, 
                         subcategories=subcategories,
                         products=products, 
                         branches=branches,
                         selected_branch_id=selected_branch_id,
                         pagination=pagination)

@app.route('/branch_products/<int:branch_id>')
@login_required
@role_required(['admin'])
def branch_products(branch_id):
    # Get the specific branch
    branch = Branch.query.get_or_404(branch_id)
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    branches = Branch.query.all()
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Filter products by the specific branch
    base_query = Product.query.filter(Product.branchid == branch_id)
    
    # Apply pagination
    pagination = base_query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    products = pagination.items
    
    return render_template('branch_products.html', 
                         branch=branch,
                         categories=categories, 
                         subcategories=subcategories,
                         products=products, 
                         branches=branches,
                         pagination=pagination)

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

# Products Routes
@app.route('/add_product', methods=['POST'])
@login_required
@role_required(['admin'])
def add_product():
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
    
    new_product = Product(
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
    
    flash('Product added successfully', 'success')
    return redirect(url_for('products'))

@app.route('/get_product/<int:id>')
@login_required
@role_required(['admin'])
def get_product(id):
    product = Product.query.get_or_404(id)
    return jsonify({
        'id': product.id,
        'name': product.name,
        'productcode': product.productcode,
        'subcategory_id': product.subcategory_id,
        'branchid': product.branchid,
        'buyingprice': product.buyingprice,
        'sellingprice': product.sellingprice,
        'stock': product.stock,
        'display': product.display,
        'image_url': product.image_url
    })

@app.route('/edit_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_product(id):
    product = Product.query.get_or_404(id)
    
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
    
    flash('Product updated successfully', 'success')
    return redirect(url_for('products'))

@app.route('/delete_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_product(id):
    try:
        product = Product.query.get_or_404(id)
        
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
        
        flash('Product deleted successfully', 'success')
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
@app.route('/add_stock/<int:product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def add_stock(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Get form data
    quantity = request.form.get('quantity')
    notes = request.form.get('notes', '')
    
    # Basic validation
    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash('Please enter a valid positive quantity', 'error')
        return redirect(url_for('products'))
    
    quantity = int(quantity)
    previous_stock = product.stock or 0
    new_stock = previous_stock + quantity
    
    # Update product stock
    product.stock = new_stock
    
    # Create stock transaction record
    stock_transaction = StockTransaction(
        productid=product_id,
        userid=current_user.id,
        transaction_type='add',
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        notes=notes
    )
    
    db.session.add(stock_transaction)
    db.session.commit()
    
    flash(f'Successfully added {quantity} units to {product.name}. New stock: {new_stock}', 'success')
    return redirect(url_for('products'))

@app.route('/remove_stock/<int:product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def remove_stock(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Get form data
    quantity = request.form.get('quantity')
    notes = request.form.get('notes', '')
    
    # Basic validation
    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash('Please enter a valid positive quantity', 'error')
        return redirect(url_for('products'))
    
    quantity = int(quantity)
    previous_stock = product.stock or 0
    
    # Check if we have enough stock
    if previous_stock < quantity:
        flash(f'Insufficient stock. Current stock: {previous_stock}, trying to remove: {quantity}', 'error')
        return redirect(url_for('products'))
    
    new_stock = previous_stock - quantity
    
    # Update product stock
    product.stock = new_stock
    
    # Create stock transaction record
    stock_transaction = StockTransaction(
        productid=product_id,
        userid=current_user.id,
        transaction_type='remove',
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        notes=notes
    )
    
    db.session.add(stock_transaction)
    db.session.commit()
    
    flash(f'Successfully removed {quantity} units from {product.name}. New stock: {new_stock}', 'success')
    return redirect(url_for('products'))

@app.route('/stock_history/<int:product_id>')
@login_required
@role_required(['admin'])
def stock_history(product_id):
    product = Product.query.get_or_404(product_id)
    transactions = StockTransaction.query.filter_by(productid=product_id).order_by(StockTransaction.created_at.desc()).all()
    
    return render_template('stock_history.html', product=product, transactions=transactions)

@app.route('/toggle_display/<int:product_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def toggle_display(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        product.display = not product.display
        db.session.commit()
        
        status = "visible" if product.display else "hidden"
        flash(f'Product "{product.name}" is now {status} in customer app', 'success')
        return redirect(url_for('products'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating product display status', 'error')
        return redirect(url_for('products'))

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
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the user. Please try again.', 'error')
            return redirect(url_for('add_user'))
    
    return render_template('add_user.html')

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
        
        try:
            db.session.commit()
            flash('User updated successfully', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the user. Please try again.', 'error')
            return redirect(url_for('edit_user', id=id))
    
    return render_template('edit_user.html', user=user)

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
        
        # Base query with joins
        base_query = db.session.query(Order).join(User).join(OrderType).join(Branch)
        
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
        
        # Get filter options
        branches = Branch.query.all()
        
        return render_template('orders.html', 
                             orders=orders, 
                             pagination=pagination,
                             branches=branches,
                             status_filter=status_filter,
                             payment_filter=payment_filter,
                             branch_filter=branch_filter)
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
        
        # Calculate order total
        total_amount = 0
        for item in order.order_items:
            if item.product and item.product.sellingprice:
                total_amount += item.product.sellingprice * item.quantity
        
        return render_template('order_details.html', order=order, total_amount=total_amount)
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
        revenue_query = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).select_from(OrderItem).join(Product, OrderItem.productid == Product.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        )
        total_revenue = revenue_query.scalar() or 0
        
        # Calculate Cost of Goods Sold (COGS)
        cogs_query = db.session.query(
            db.func.sum(OrderItem.quantity * Product.buyingprice)
        ).select_from(OrderItem).join(Product, OrderItem.productid == Product.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'paid',
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
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).count()
        
        # Get top selling products
        top_products = db.session.query(
            Product.name,
            db.func.sum(OrderItem.quantity).label('total_quantity'),
            db.func.sum(OrderItem.quantity * Product.sellingprice).label('total_revenue')
        ).select_from(Product).join(OrderItem, Product.id == OrderItem.productid).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).group_by(Product.id, Product.name).order_by(
            db.func.sum(OrderItem.quantity).desc()
        ).limit(10).all()
        
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
        inventory_value = db.session.query(
            db.func.sum(Product.stock * Product.buyingprice)
        ).filter(Product.stock > 0).scalar() or 0
        
        # Accounts Receivable (pending payments)
        accounts_receivable = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).select_from(OrderItem).join(Product, OrderItem.productid == Product.id).join(
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
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).select_from(OrderItem).join(Product, OrderItem.productid == Product.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'paid',
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        total_cogs = db.session.query(
            db.func.sum(OrderItem.quantity * Product.buyingprice)
        ).select_from(OrderItem).join(Product, OrderItem.productid == Product.id).join(
            Order, OrderItem.orderid == Order.id
        ).filter(
            Order.payment_status == 'paid',
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
            db.func.sum(Product.stock * Product.buyingprice).label('value')
        ).select_from(Category).join(SubCategory, Category.id == SubCategory.category_id).join(
            Product, SubCategory.id == Product.subcategory_id
        ).filter(Product.stock > 0).group_by(Category.id, Category.name).all()
        
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
        
        # Get all branches with pagination
        pagination = Branch.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        branches = pagination.items
        print(f"Branches found: {len(branches)}")
        
        return render_template('branches.html', branches=branches, pagination=pagination)
    except Exception as e:
        print(f"Error in branches route: {e}")
        db.session.rollback()
        flash('An error occurred while loading branches. Please try again.', 'error')
        return redirect(url_for('index'))

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
        if branch.products or branch.orders:
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
        total_products = Product.query.filter_by(branchid=branch_id).count()
        total_orders = Order.query.filter_by(branchid=branch_id).count()
        
        # Get recent orders for this branch
        recent_orders = Order.query.filter_by(branchid=branch_id).order_by(Order.created_at.desc()).limit(10).all()
        
        # Get products in this branch
        products = Product.query.filter_by(branchid=branch_id).all()
        
        # Calculate branch revenue
        branch_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).join(Product).join(Order).filter(
            Order.branchid == branch_id,
            Order.payment_status == 'paid'
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
        print("Categories route accessed")
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get all categories with pagination
        pagination = Category.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        categories = pagination.items
        print(f"Categories found: {len(categories)}")
        
        return render_template('categories.html', categories=categories, pagination=pagination)
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
        subcategories = SubCategory.query.filter_by(category_id=category_id).all()
        subcategory_ids = [sub.id for sub in subcategories]
        
        # Handle both old and new product structures
        if subcategory_ids:
            # New structure: products through subcategories
            total_products = Product.query.filter(Product.subcategory_id.in_(subcategory_ids)).count()
            products = Product.query.filter(Product.subcategory_id.in_(subcategory_ids)).all()
            
            # Calculate category revenue
            category_revenue = db.session.query(
                db.func.sum(OrderItem.quantity * Product.sellingprice)
            ).join(Product).join(Order).filter(
                Product.subcategory_id.in_(subcategory_ids),
                Order.payment_status == 'paid'
            ).scalar() or 0
            
            # Get products by branch
            products_by_branch = db.session.query(
                Branch.name,
                db.func.count(Product.id).label('product_count')
            ).join(Product).filter(
                Product.subcategory_id.in_(subcategory_ids)
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
    categories = Category.query.all()
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
    categories = Category.query.all()
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
        total_products = Product.query.filter_by(subcategory_id=subcategory_id).count()
        
        # Get products in this subcategory
        products = Product.query.filter_by(subcategory_id=subcategory_id).all()
        
        # Calculate subcategory revenue
        subcategory_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).join(Product).join(Order).filter(
            Product.subcategory_id == subcategory_id,
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        # Get products by branch
        products_by_branch = db.session.query(
            Branch.name,
            db.func.count(Product.id).label('product_count')
        ).join(Product).filter(
            Product.subcategory_id == subcategory_id
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

# Product Description Management Routes
@app.route('/product_descriptions/<int:product_id>')
@login_required
@role_required(['admin'])
def product_descriptions(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        descriptions = ProductDescription.query.filter_by(
            product_id=product_id, is_active=True
        ).order_by(ProductDescription.sort_order, ProductDescription.created_at).all()
        
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
    product = Product.query.get_or_404(product_id)
    
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
            flash('Product description added successfully', 'success')
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
            flash('Product description updated successfully', 'success')
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
        
        flash('Product description deleted successfully', 'success')
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
            
            flash('Purchase Order created successfully', 'success')
            return redirect(url_for('edit_purchase_order', id=new_po.id))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating purchase order: {e}")
            flash('An error occurred while creating purchase order.', 'error')
            return redirect(url_for('add_purchase_order'))
    
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    branches = Branch.query.all()
    products = Product.query.all()
    
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
            products = Product.query.all()
            
            print(f"✅ Data prepared:")
            print(f"   - Suppliers count: {len(suppliers)}")
            print(f"   - Branches count: {len(branches)}")
            print(f"   - Products count: {len(products)}")
            
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
                    print(f"     * Product Name: {item.product_name}")
                    print(f"     * Product Code: {item.product_code}")
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
        
        # Test Product model
        product_count = Product.query.count()
        print(f"✅ Product model working. Total products: {product_count}")
        
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
        
        if not product_code or not product_name or not quantity:
            flash('Product Code, Product Name, and Quantity are required', 'error')
            return redirect(url_for('edit_purchase_order', id=po_id))
        
        try:
            quantity = int(quantity)
            unit_price = Decimal(str(unit_price)) if unit_price else None
            total_price = quantity * unit_price if unit_price else None
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
                product_code = request.form.get('product_code')
                product_name = request.form.get('product_name')
                quantity = request.form.get('quantity')
                unit_price = request.form.get('unit_price')
                notes = request.form.get('notes')
                
                print(f"📝 Form data received:")
                print(f"   - product_code: {product_code}")
                print(f"   - product_name: {product_name}")
                print(f"   - quantity: {quantity}")
                print(f"   - unit_price: {unit_price}")
                print(f"   - notes: {notes}")
                
                # Validate required fields
                if not product_code or not product_name or not quantity:
                    print(f"❌ Missing required fields")
                    flash('Product Code, Product Name, and Quantity are required', 'error')
                    return redirect(url_for('edit_po_item', item_id=item_id))
                
                # Validate numeric fields
                try:
                    quantity = int(quantity)
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
                po_item.unit_price = unit_price
                po_item.notes = notes
                
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
        
        # Recreate the ABZ Hardware letterhead manually
        
        # Try to load the logo for the left side
        try:
            logo_path = os.path.join(app.static_folder, 'assets', 'img', 'logo.png')
            if os.path.exists(logo_path):
                logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
                logo_cell = logo_image
            else:
                # Fallback to text if logo not found
                logo_cell = Paragraph('''
                <para align=left>
                <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
                <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
                <b><font size=14 color="#1a365d">LIMITED</font></b>
                </para>
                ''', normal_style)
        except Exception as e:
            print(f"Error loading logo: {e}")
            # Fallback to text if logo fails to load
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
            <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
            <b><font size=14 color="#1a365d">LIMITED</font></b>
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
            <font size=10 color="#666666">0711 732 341 or 0725 000 055</font> 📞<br/>
            <font size=10 color="#666666">info@abzhardware.co.ke</font> ✉<br/>
            <font size=10 color="#666666">www.abzhardware.co.ke</font> 🌐
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
        separator_table = Table(separator_data, colWidths=[7*inch], rowHeights=[0.15*inch])
        separator_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4b942')),  # Yellow color
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1a365d')),   # Dark blue border
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
        <b>Branch:</b> {po.branch.name if po.branch else 'N/A'}<br/>
        <b>Expected Delivery:</b> {po.expected_delivery_date.strftime('%B %d, %Y') if po.expected_delivery_date else 'Not specified'}
        """
        elements.append(Paragraph(po_details, normal_style))
        elements.append(Spacer(1, 30))
        
        # Items Table (simplified: Product Code, Product Name, Quantity only)
        if po.items:
            elements.append(Paragraph("ITEMS ORDERED", heading_style))
            
            # Table data - simplified to 3 columns only
            data = [['Product Code', 'Product Name', 'Quantity']]
            
            for item in po.items:
                data.append([
                    item.product_code or 'N/A',
                    item.product_name or 'N/A',
                    str(item.quantity) if item.quantity else '0'
                ])
            
            # Create table with 3 columns - adjusted for wider page
            table = Table(data, colWidths=[2.2*inch, 4.5*inch, 1.5*inch])
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
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Product Code center
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Product Name left
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # Quantity center
                
                # Padding
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 30))
        else:
            elements.append(Paragraph("No items in this purchase order.", normal_style))
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
        Generated on {datetime.now(EAT).strftime('%B %d, %Y at %I:%M %p')} by {current_user.firstname} {current_user.lastname}<br/>
        This is a computer-generated document and does not require a signature.
        </font>
        </para>
        """
        elements.append(Spacer(1, 50))
        elements.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF data
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Create response
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="PO_{po.po_number}.pdf"'
        
        return response
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        flash('An error occurred while generating the PDF.', 'error')
        return redirect(url_for('purchase_orders'))

# Error handlers
@app.errorhandler(IntegrityError)
def handle_integrity_error(error):
    db.session.rollback()
    flash('Cannot perform this action. The record has associated data that prevents deletion.', 'error')
    # Try to redirect back to the referring page, or to index if no referrer
    return redirect(request.referrer or url_for('index'))

@app.errorhandler(Exception)
def handle_general_error(error):
    db.session.rollback()
    flash('An unexpected error occurred. Please try again.', 'error')
    # Try to redirect back to the referring page, or to index if no referrer
    return redirect(request.referrer or url_for('index'))

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