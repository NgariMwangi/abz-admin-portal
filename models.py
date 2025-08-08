from extensions import db
from datetime import datetime, timezone, timedelta

EAT = timezone(timedelta(hours=3))


class Branch(db.Model):
    __tablename__ = 'branch'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    location = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    image_url = db.Column(db.String, nullable=True)
    products = db.relationship('Product', backref='branch', lazy=True)
    orders = db.relationship('Order', backref='branch', lazy=True)


class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    image_url = db.Column(db.String, nullable=True)
    sub_categories = db.relationship('SubCategory', backref='category', lazy=True)
    
    @property
    def products(self):
        """Get all products in this category through subcategories"""
        from sqlalchemy import and_
        # Check if this category has any subcategories
        subcategories = SubCategory.query.filter_by(category_id=self.id).all()
        if not subcategories:
            return []
        
        subcategory_ids = [sub.id for sub in subcategories]
        return Product.query.filter(Product.subcategory_id.in_(subcategory_ids)).all()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False, unique=True)
    firstname = db.Column(db.String, nullable=False)
    lastname = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    role = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    phone = db.Column(db.String, nullable=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    stock_transactions = db.relationship('StockTransaction', backref='user', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
    
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    branchid = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    image_url = db.Column(db.String, nullable=True)
    buyingprice = db.Column(db.Integer, nullable=True)
    sellingprice = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, nullable=True)
    productcode = db.Column(db.String, nullable=True)
    display = db.Column(db.Boolean, default=True)  # Controls visibility in customer app
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    subcategory_id = db.Column(db.Integer, db.ForeignKey('sub_category.id'), nullable=True)
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    stock_transactions = db.relationship('StockTransaction', backref='product', lazy=True)
    descriptions = db.relationship('ProductDescription', backref='product', lazy=True)


class ProductDescription(db.Model):
    __tablename__ = 'product_descriptions'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    title = db.Column(db.String, nullable=False)  # e.g., "Overview", "Specifications", "Features"
    content = db.Column(db.Text, nullable=False)  # Rich text content
    content_type = db.Column(db.String, default='text')  # text, html, markdown
    language = db.Column(db.String, default='en')  # Language code (en, sw, etc.)
    is_active = db.Column(db.Boolean, default=True)  # Can be disabled without deleting
    sort_order = db.Column(db.Integer, default=0)  # For ordering multiple descriptions
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))


class StockTransaction(db.Model):
    __tablename__ = 'stock_transactions'
    id = db.Column(db.Integer, primary_key=True)
    productid = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    userid = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_type = db.Column(db.String, nullable=False)  # 'add' or 'remove'
    quantity = db.Column(db.Integer, nullable=False)
    previous_stock = db.Column(db.Integer, nullable=False)
    new_stock = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))


class OrderType(db.Model):
    __tablename__ = 'ordertypes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

    orders = db.relationship('Order', backref='ordertype', lazy=True)


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ordertypeid = db.Column(db.Integer, db.ForeignKey('ordertypes.id'), nullable=False)
    branchid = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    approvalstatus = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    payment_status = db.Column(db.String, default='pending')  # pending, paid, failed, refunded

    order_items = db.relationship('OrderItem', backref='order', lazy=True)
    payments = db.relationship('Payment', backref='order', lazy=True)

class OrderItem(db.Model):
    __tablename__ = 'orderitems'
    id = db.Column(db.Integer, primary_key=True)
    orderid = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    productid = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    buying_price = db.Column(db.Numeric(10, 2), nullable=True)  # Product buying price at time of order
    original_price = db.Column(db.Numeric(10, 2), nullable=True)  # Original product selling price
    negotiated_price = db.Column(db.Numeric(10, 2), nullable=True)  # Negotiated price (if any)
    final_price = db.Column(db.Numeric(10, 2), nullable=True)  # Final price used for calculation
    negotiation_notes = db.Column(db.String, nullable=True)  # Notes about the negotiation
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))

    


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    orderid = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    userid = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String, nullable=False)  # cash, card, mobile_money, bank_transfer
    payment_status = db.Column(db.String, nullable=False)  # pending, completed, failed, refunded
    transaction_id = db.Column(db.String, nullable=True)  # External payment gateway transaction ID
    reference_number = db.Column(db.String, nullable=True)  # Internal reference number
    notes = db.Column(db.String, nullable=True)
    payment_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))


class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    orderid = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    invoice_number = db.Column(db.String, nullable=False, unique=True)  # INV-YYYYMMDD-XXXX
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), default=0.00)
    discount_amount = db.Column(db.Numeric(10, 2), default=0.00)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String, default='pending')  # pending, paid, overdue, cancelled
    due_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))

    order = db.relationship('Order', backref='invoices', lazy=True)


class Receipt(db.Model):
    __tablename__ = 'receipts'
    id = db.Column(db.Integer, primary_key=True)
    paymentid = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False)
    orderid = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    receipt_number = db.Column(db.String, nullable=False, unique=True)  # RCP-YYYYMMDD-XXXX
    payment_amount = db.Column(db.Numeric(10, 2), nullable=False)
    previous_balance = db.Column(db.Numeric(10, 2), nullable=False)
    remaining_balance = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String, nullable=False)
    reference_number = db.Column(db.String, nullable=True)
    transaction_id = db.Column(db.String, nullable=True)
    notes = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))

    payment = db.relationship('Payment', backref='receipts', lazy=True)
    order = db.relationship('Order', backref='receipts', lazy=True)


class SubCategory(db.Model):
    __tablename__ = 'sub_category'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    image_url = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))

    products = db.relationship('Product', backref='sub_category', lazy=True)


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String, nullable=False)  # rent, utilities, salaries, supplies, marketing, etc.
    expense_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String, nullable=True)  # cash, bank_transfer, card, mobile_money
    receipt_url = db.Column(db.String, nullable=True)  # URL to uploaded receipt image
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Who recorded the expense
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who approved the expense
    status = db.Column(db.String, default='pending')  # pending, approved, rejected
    approval_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    
    # Relationships
    branch = db.relationship('Branch', backref='expenses', lazy=True)
    user = db.relationship('User', foreign_keys=[user_id], backref='expenses_recorded', lazy=True)
    approver = db.relationship('User', foreign_keys=[approved_by], backref='expenses_approved', lazy=True)


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    contact_person = db.Column(db.String, nullable=True)
    email = db.Column(db.String, nullable=True)
    phone = db.Column(db.String, nullable=True)
    address = db.Column(db.Text, nullable=True)
    tax_number = db.Column(db.String, nullable=True)
    payment_terms = db.Column(db.String, nullable=True)  # net 30, net 60, etc.
    credit_limit = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    
    # Relationships
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True)


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String, nullable=False, unique=True)  # PO-YYYYMMDD-XXXX
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Who created the PO
    order_date = db.Column(db.Date, nullable=False)
    expected_delivery_date = db.Column(db.Date, nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String, default='draft')  # draft, submitted, approved, ordered, received, cancelled
    payment_status = db.Column(db.String, default='pending')  # pending, partial, paid
    payment_method = db.Column(db.String, nullable=True)  # cash, bank_transfer, check
    notes = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    
    # Relationships
    branch = db.relationship('Branch', backref='purchase_orders', lazy=True)
    user = db.relationship('User', foreign_keys=[user_id], backref='purchase_orders_created', lazy=True)
    approver = db.relationship('User', foreign_keys=[approved_by], backref='purchase_orders_approved', lazy=True)
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')


class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    received_quantity = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(EAT), onupdate=lambda: datetime.now(EAT))
    
    # Relationships
    product = db.relationship('Product', backref='purchase_order_items', lazy=True)
