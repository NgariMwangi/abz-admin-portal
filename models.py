from extensions import db
from datetime import datetime


class Branch(db.Model):
    __tablename__ = 'branch'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    location = db.Column(db.String, nullable=False)

    products = db.relationship('Product', backref='branch', lazy=True)
    orders = db.relationship('Order', backref='branch', lazy=True)


class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)

    products = db.relationship('Product', backref='category', lazy=True)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False, unique=True)
    firstname = db.Column(db.String, nullable=False)
    lastname = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    role = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # phone = db.Column(db.String, nullable=True)
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
    categoryid = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    branchid = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    image_url = db.Column(db.String, nullable=True)
    buyingprice = db.Column(db.Integer, nullable=True)
    sellingprice = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, nullable=True)
    productcode = db.Column(db.String, nullable=True)
    display = db.Column(db.Boolean, default=True)  # Controls visibility in customer app
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    stock_transactions = db.relationship('StockTransaction', backref='product', lazy=True)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    quantity= db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payment = db.relationship('Payment', backref='receipts', lazy=True)
    order = db.relationship('Order', backref='receipts', lazy=True)
