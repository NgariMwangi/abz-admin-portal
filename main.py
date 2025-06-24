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

db = SQLAlchemy()
from models import Branch, Category, User, Product, OrderType, Order, OrderItem, StockTransaction

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

@app.route('/add_category', methods=['POST'])
@login_required
@role_required(['admin'])
def add_category():
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('products'))
    
    new_category = Category(name=name, description=description)
    db.session.add(new_category)
    db.session.commit()
    
    flash('Category added successfully', 'success')
    return redirect(url_for('products'))

@app.route('/edit_category/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_category(id):
    category = Category.query.get_or_404(id)
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('products'))
    
    category.name = name
    category.description = description
    db.session.commit()
    
    flash('Category updated successfully', 'success')
    return redirect(url_for('products'))

@app.route('/delete_category/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_category(id):
    try:
        category = Category.query.get_or_404(id)
        
        # Check if category has products
        if category.products:
            flash('Cannot delete category with associated products', 'error')
            return redirect(url_for('products'))
        
        db.session.delete(category)
        db.session.commit()
        
        flash('Category deleted successfully', 'success')
        return redirect(url_for('products'))
    except IntegrityError as e:
        db.session.rollback()
        flash('Cannot delete this category. It has associated products or other related records.', 'error')
        return redirect(url_for('products'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the category. Please try again.', 'error')
        return redirect(url_for('products'))

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

# Error handlers
@app.errorhandler(IntegrityError)
def handle_integrity_error(error):
    db.session.rollback()
    flash('Cannot perform this action. The record has associated data that prevents deletion.', 'error')
    return redirect(request.referrer or url_for('products'))

@app.errorhandler(Exception)
def handle_general_error(error):
    db.session.rollback()
    flash('An unexpected error occurred. Please try again.', 'error')
    return redirect(request.referrer or url_for('products'))

if __name__ == '__main__':
    app.run(debug=True)