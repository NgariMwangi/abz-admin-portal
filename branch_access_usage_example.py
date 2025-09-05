"""
Example of how to use branch access control in your routes

This file shows how to integrate the branch access functionality
into your existing routes and add access control.
"""

from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
from branch_access import check_branch_access, require_branch_access, get_user_accessible_branches, filter_orders_by_branch_access
from models import Order, Product, Branch

# Example 1: Using the decorator for branch-specific routes
@app.route('/branch/<int:branch_id>/orders')
@login_required
@require_branch_access
def branch_orders(branch_id):
    """View orders for a specific branch - access controlled"""
    # This route will automatically check if user has access to branch_id
    # If not, user will be redirected with an error message
    
    orders = Order.query.filter_by(branchid=branch_id).all()
    return render_template('branch_orders.html', orders=orders, branch_id=branch_id)

# Example 2: Manual access check in route
@app.route('/branch/<int:branch_id>/products')
@login_required
def branch_products(branch_id):
    """View products for a specific branch - manual access check"""
    
    # Check if user has access to this branch
    if not check_branch_access(current_user, branch_id):
        flash('You do not have access to this branch.', 'error')
        return redirect(url_for('index'))
    
    # Get branch information
    branch = Branch.query.get_or_404(branch_id)
    products = Product.query.filter_by(branchid=branch_id).all()
    
    return render_template('branch_products.html', products=products, branch=branch)

# Example 3: Filtering data based on user's accessible branches
@app.route('/orders')
@login_required
def orders():
    """View all orders - filtered by user's branch access"""
    
    # Get all orders
    all_orders = Order.query.all()
    
    # Filter orders based on user's branch access
    accessible_orders = filter_orders_by_branch_access(all_orders, current_user)
    
    return render_template('orders.html', orders=accessible_orders)

# Example 4: Getting user's accessible branches for dropdowns
@app.route('/reports')
@login_required
def reports():
    """Reports page - show only accessible branches"""
    
    # Get branches the user can access
    accessible_branches = get_user_accessible_branches(current_user)
    
    return render_template('reports.html', branches=accessible_branches)

# Example 5: Admin route that shows all users with branch access info
@app.route('/admin/users')
@login_required
@role_required(['admin'])
def admin_users():
    """Admin view of all users with branch access information"""
    
    users = User.query.all()
    
    # Add branch access summary for each user
    for user in users:
        user.branch_access_summary = get_branch_access_summary(user)
    
    return render_template('admin_users.html', users=users)

# Example 6: Creating a new order with branch access validation
@app.route('/create_order', methods=['GET', 'POST'])
@login_required
def create_order():
    """Create a new order - validate branch access"""
    
    if request.method == 'POST':
        branch_id = request.form.get('branch_id', type=int)
        
        # Validate branch access
        if not check_branch_access(current_user, branch_id):
            flash('You do not have access to create orders for this branch.', 'error')
            return redirect(url_for('create_order'))
        
        # Create the order
        # ... order creation logic ...
        
        flash('Order created successfully!', 'success')
        return redirect(url_for('orders'))
    
    # Get accessible branches for the form
    accessible_branches = get_user_accessible_branches(current_user)
    return render_template('create_order.html', branches=accessible_branches)

# Example 7: Using in templates
"""
In your templates, you can use the branch access methods:

{% if current_user.has_branch_access(branch.id) %}
    <a href="{{ url_for('branch_orders', branch_id=branch.id) }}" class="btn btn-primary">
        View Orders
    </a>
{% else %}
    <span class="text-muted">No access to this branch</span>
{% endif %}

{% for branch in current_user.get_accessible_branches() %}
    <option value="{{ branch.id }}">{{ branch.name }}</option>
{% endfor %}
"""

# Example 8: Bulk operations with branch access
@app.route('/bulk_update_products', methods=['POST'])
@login_required
def bulk_update_products():
    """Bulk update products - respect branch access"""
    
    product_ids = request.form.getlist('product_ids')
    branch_id = request.form.get('branch_id', type=int)
    
    # Check branch access
    if not check_branch_access(current_user, branch_id):
        flash('You do not have access to update products in this branch.', 'error')
        return redirect(url_for('products'))
    
    # Update products
    products = Product.query.filter(
        Product.id.in_(product_ids),
        Product.branchid == branch_id
    ).all()
    
    # ... update logic ...
    
    flash(f'Updated {len(products)} products successfully!', 'success')
    return redirect(url_for('products'))

# Example 9: API endpoint with branch access
@app.route('/api/branch/<int:branch_id>/stats')
@login_required
def api_branch_stats(branch_id):
    """API endpoint for branch statistics - access controlled"""
    
    if not check_branch_access(current_user, branch_id):
        return {'error': 'Access denied'}, 403
    
    # Get statistics for the branch
    stats = {
        'total_orders': Order.query.filter_by(branchid=branch_id).count(),
        'total_products': Product.query.filter_by(branchid=branch_id).count(),
        # ... more stats
    }
    
    return stats

# Example 10: Middleware for all branch-related routes
def check_branch_access_middleware():
    """Middleware to check branch access for all routes with branch_id parameter"""
    
    if request.view_args and 'branch_id' in request.view_args:
        branch_id = request.view_args['branch_id']
        if not check_branch_access(current_user, branch_id):
            flash('You do not have access to this branch.', 'error')
            return redirect(url_for('index'))
    
    return None

# Register the middleware
@app.before_request
def before_request():
    if current_user.is_authenticated:
        return check_branch_access_middleware()
