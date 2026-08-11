import enum
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

class OrderStatus(str, enum.Enum):
    DRAFT = "Draft"
    ORDERED = "Ordered"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"

class MovementType(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    ORDER_RECEIPT = "ORDER RECEIPT"
    SUPPLIER_RETURN = "SUPPLIER RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    SALE = "SALE"
    SALE_REFUND = "SALE REFUND"

class SaleStatus(str, enum.Enum):
    SOLD = "Sold"
    REFUNDED = "Refunded"

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    contact_person = Column(String(100))
    email = Column(String(100))
    phone = Column(String(50))

    products = relationship("Product", back_populates="supplier")
    orders = relationship("PurchaseOrder", back_populates="supplier")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(50), default="General")
    quantity = Column(Integer, default=0)
    min_threshold = Column(Integer, default=5)
    purchase_price_excl_tax = Column(Float, default=0.0)  # Price Excl. Tax (HT)
    selling_price_excl_tax = Column(Float, default=0.0)   # Price Excl. Tax (HT)
    vat_rate = Column(Float, default=20.0)                # VAT Rate (20%)
    location = Column(String(50), default="A-01")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    supplier = relationship("Supplier", back_populates="products")
    movements = relationship("StockMovement", back_populates="product", cascade="all, delete-orphan")

    @property
    def selling_price_incl_tax(self) -> float:
        """Calculates price including VAT (TTC)"""
        return self.selling_price_excl_tax * (1 + self.vat_rate / 100.0)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference = Column(String(50), unique=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.DRAFT)
    order_date = Column(DateTime, default=datetime.now)
    total_excl_tax = Column(Float, default=0.0)
    vat_rate = Column(Float, default=20.0)

    supplier = relationship("Supplier", back_populates="orders")
    items = relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def total_incl_tax(self) -> float:
        return self.total_excl_tax * (1 + self.vat_rate / 100.0)

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    unit_cost_excl_tax = Column(Float, nullable=False)

    order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product")

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference = Column(String(50), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_excl_tax = Column(Float, nullable=False)
    vat_rate = Column(Float, default=20.0)
    total_excl_tax = Column(Float, default=0.0)
    sale_date = Column(DateTime, default=datetime.now)
    status = Column(Enum(SaleStatus), default=SaleStatus.SOLD)
    refund_date = Column(DateTime, nullable=True)

    product = relationship("Product")

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    type = Column(Enum(MovementType), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)

    product = relationship("Product", back_populates="movements")

# Database Setup
DB_URL = "sqlite:///stock_management.db"
engine = create_engine(DB_URL, echo=False)

@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Enforce foreign key constraints so linked records cannot be orphaned."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)