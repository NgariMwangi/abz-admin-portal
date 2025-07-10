from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
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
from models import Branch, Category, User, Product, OrderType, Order, OrderItem, StockTransaction, Payment

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
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        print(email)
        print(password)
        
        user = User.query.filter_by(email=email, password=password).first()
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

# Categories Routes
@app.route('/products')
@login_required
@role_required(['admin'])
def products():
    categories = Category.query.all()
    branches = Branch.query.all()
    
    # Get selected branch from query parameter
    selected_branch_id = request.args.get('branch_id', type=int)
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)  # Default 10 items per page
    
    # Base query
    if selected_branch_id:
        # Filter products by selected branch
        base_query = Product.query.join(Category).filter(Product.branchid == selected_branch_id)
    else:
        # Show all products if no branch is selected
        base_query = Product.query.join(Category)
    
    # Apply pagination
    pagination = base_query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    products = pagination.items
    
    return render_template('products.html', 
                         categories=categories, 
                         products=products, 
                         branches=branches,
                         selected_branch_id=selected_branch_id,
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
        
        new_category = Category(name=name, description=description)
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
    categoryid = request.form.get('categoryid')
    branchid = request.form.get('branchid')  # Get branch ID from form
    buyingprice = request.form.get('buyingprice')
    sellingprice = request.form.get('sellingprice')
    stock = request.form.get('stock')
    productcode = request.form.get('productcode')
    
    # Basic validation
    if not name or not categoryid or not branchid:
        flash('Name, Category, and Branch are required', 'error')
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
        categoryid=categoryid,
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

@app.route('/edit_product/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    # Get form data
    product.name = request.form.get('name')
    product.categoryid = request.form.get('categoryid')
    product.branchid = request.form.get('branchid')  # Get branch ID from form
    product.buyingprice = int(request.form.get('buyingprice')) if request.form.get('buyingprice') else None
    product.sellingprice = int(request.form.get('sellingprice')) if request.form.get('sellingprice') else None
    product.stock = int(request.form.get('stock')) if request.form.get('stock') else None
    product.productcode = request.form.get('productcode')
    
    # Handle display field
    product.display = request.form.get('display') == 'on'
    
    # Basic validation
    if not product.name or not product.categoryid or not product.branchid:
        flash('Name, Category, and Branch are required', 'error')
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
            password=password,  # In production, you should hash this password
            role=role
        )
        
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
            user.password = password  # In production, you should hash this password
        
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
        order.approved_at = datetime.utcnow()
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
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Convert to datetime objects
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Calculate Revenue (from completed orders)
        revenue_query = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).join(Product).join(Order).filter(
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        )
        total_revenue = revenue_query.scalar() or 0
        
        # Calculate Cost of Goods Sold (COGS)
        cogs_query = db.session.query(
            db.func.sum(OrderItem.quantity * Product.buyingprice)
        ).join(Product).join(Order).filter(
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        )
        total_cogs = cogs_query.scalar() or 0
        
        # Calculate Gross Profit
        gross_profit = total_revenue - total_cogs
        
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
        ).join(OrderItem).join(Order).filter(
            Order.payment_status == 'paid',
            Order.created_at >= start_dt,
            Order.created_at <= end_dt
        ).group_by(Product.id, Product.name).order_by(
            db.func.sum(OrderItem.quantity).desc()
        ).limit(10).all()
        
        # Calculate profit margin
        profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return render_template('profit_loss.html',
                             start_date=start_date,
                             end_date=end_date,
                             total_revenue=total_revenue,
                             total_cogs=total_cogs,
                             gross_profit=gross_profit,
                             profit_margin=profit_margin,
                             total_orders=total_orders,
                             paid_orders=paid_orders,
                             top_products=top_products)
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
            as_of_date = datetime.now().strftime('%Y-%m-%d')
        
        as_of_dt = datetime.strptime(as_of_date, '%Y-%m-%d')
        
        # Calculate Assets
        # Inventory Value (current stock * buying price)
        inventory_value = db.session.query(
            db.func.sum(Product.stock * Product.buyingprice)
        ).filter(Product.stock > 0).scalar() or 0
        
        # Accounts Receivable (pending payments)
        accounts_receivable = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).join(Product).join(Order).filter(
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
        ).join(Product).join(Order).filter(
            Order.payment_status == 'paid',
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        total_cogs = db.session.query(
            db.func.sum(OrderItem.quantity * Product.buyingprice)
        ).join(Product).join(Order).filter(
            Order.payment_status == 'paid',
            Order.created_at <= as_of_dt
        ).scalar() or 0
        
        retained_earnings = total_revenue - total_cogs
        
        total_liabilities_equity = accounts_payable + retained_earnings
        
        # Get inventory breakdown by category
        inventory_by_category = db.session.query(
            Category.name,
            db.func.sum(Product.stock * Product.buyingprice).label('value')
        ).join(Product).filter(Product.stock > 0).group_by(Category.id, Category.name).all()
        
        # Get recent transactions
        recent_transactions = db.session.query(
            Order, User, Branch
        ).join(User).join(Branch).filter(
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
        
        # Get category statistics
        total_products = Product.query.filter_by(categoryid=category_id).count()
        
        # Get products in this category
        products = Product.query.filter_by(categoryid=category_id).all()
        
        # Calculate category revenue
        category_revenue = db.session.query(
            db.func.sum(OrderItem.quantity * Product.sellingprice)
        ).join(Product).join(Order).filter(
            Product.categoryid == category_id,
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        # Get products by branch
        products_by_branch = db.session.query(
            Branch.name,
            db.func.count(Product.id).label('product_count')
        ).join(Product).filter(
            Product.categoryid == category_id
        ).group_by(Branch.id, Branch.name).all()
        
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

if __name__ == '__main__':
    app.run(debug=True)