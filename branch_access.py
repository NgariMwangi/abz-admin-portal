"""
Branch Access Control Utilities

This module provides utilities for managing and checking user branch access.
"""

from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user
from models import User, Branch
from sqlalchemy import or_


def check_branch_access(user, branch_id):
    """
    Check if a user has access to a specific branch.
    
    Args:
        user: User object
        branch_id: ID of the branch to check access for
        
    Returns:
        bool: True if user has access, False otherwise
    """
    if not user:
        return False
    
    # Admin users always have access
    if user.role == 'admin':
        return True
    
    # Check branch access
    return user.has_branch_access(branch_id)


def require_branch_access(f):
    """
    Decorator to require branch access for a route.
    Expects branch_id as a URL parameter or form data.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        # Get branch_id from URL parameters or form data
        branch_id = kwargs.get('branch_id') or request.form.get('branch_id') or request.args.get('branch_id')
        
        if branch_id:
            try:
                branch_id = int(branch_id)
                if not check_branch_access(current_user, branch_id):
                    flash('You do not have access to this branch.', 'error')
                    return redirect(url_for('index'))
            except (ValueError, TypeError):
                flash('Invalid branch ID.', 'error')
                return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def get_user_accessible_branches(user):
    """
    Get all branches that a user has access to.
    
    Args:
        user: User object
        
    Returns:
        list: List of Branch objects
    """
    if not user:
        return []
    
    # Admin users have access to all branches
    if user.role == 'admin':
        return Branch.query.all()
    
    return user.get_accessible_branches()


def filter_orders_by_branch_access(orders, user):
    """
    Filter orders to only include those from branches the user has access to.
    
    Args:
        orders: Query object or list of Order objects
        user: User object
        
    Returns:
        Filtered orders
    """
    if not user:
        return []
    
    # Admin users can see all orders
    if user.role == 'admin':
        return orders
    
    # Get accessible branch IDs
    if user.has_all_branch_access():
        return orders
    
    accessible_branch_ids = user.accessible_branch_ids or []
    if not accessible_branch_ids:
        return []  # No access to any branches
    
    # Filter orders by accessible branches
    if hasattr(orders, 'filter'):
        # SQLAlchemy query object
        return orders.filter(orders.column_descriptions[0]['entity'].branchid.in_(accessible_branch_ids))
    else:
        # List of orders
        return [order for order in orders if order.branchid in accessible_branch_ids]


def get_branch_access_summary(user):
    """
    Get a summary of user's branch access for display purposes.
    
    Args:
        user: User object
        
    Returns:
        dict: Summary information about branch access
    """
    if not user:
        return {'has_access': False, 'branches': [], 'access_type': 'none'}
    
    if user.role == 'admin':
        all_branches = Branch.query.all()
        return {
            'has_access': True,
            'branches': all_branches,
            'access_type': 'admin',
            'branch_count': len(all_branches)
        }
    
    if user.has_all_branch_access():
        all_branches = Branch.query.all()
        return {
            'has_access': True,
            'branches': all_branches,
            'access_type': 'all',
            'branch_count': len(all_branches)
        }
    
    accessible_branches = user.get_accessible_branches()
    return {
        'has_access': len(accessible_branches) > 0,
        'branches': accessible_branches,
        'access_type': 'limited',
        'branch_count': len(accessible_branches)
    }


# Query helpers for database operations
def get_users_with_branch_access(branch_id):
    """
    Get all users who have access to a specific branch.
    
    Args:
        branch_id: ID of the branch
        
    Returns:
        Query: SQLAlchemy query object
    """
    return User.query.filter(
        or_(
            User.accessible_branch_ids.is_(None),  # NULL = all branches
            User.accessible_branch_ids == [],  # Empty list = all branches
            User.accessible_branch_ids.contains([branch_id])  # Contains specific branch
        )
    )


def get_users_with_multiple_branch_access(branch_ids):
    """
    Get users who have access to any of the specified branches.
    
    Args:
        branch_ids: List of branch IDs
        
    Returns:
        Query: SQLAlchemy query object
    """
    conditions = [
        User.accessible_branch_ids.is_(None),  # NULL = all branches
        User.accessible_branch_ids == []  # Empty list = all branches
    ]
    
    for branch_id in branch_ids:
        conditions.append(User.accessible_branch_ids.contains([branch_id]))
    
    return User.query.filter(or_(*conditions))
