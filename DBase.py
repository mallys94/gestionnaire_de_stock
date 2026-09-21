import enum
import glob
import os
import sqlite3
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, event
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

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    contact_person = Column(String(100))
    email = Column(String(100))
    phone = Column(String(50))

    sales = relationship("Sale", back_populates="customer")

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
    payment_status = Column(String(20), default="PAID")  # PAID / PENDING

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
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    payment_status = Column(String(20), default="PAID")  # PAID / CREDIT (credit = pending/unpaid)
    refundable = Column(Boolean, default=True)  # True = 14-day refund window applies

    product = relationship("Product")
    customer = relationship("Customer", back_populates="sales")

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
DB_URL = "sqlite:///" + os.environ.get("STOCK_DB", "stock_management.db")
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
    _migrate_existing_db()


def _migrate_existing_db():
    """Add columns/tables that are missing in databases created by older versions."""
    with engine.begin() as conn:
        _ensure_column(conn, "sales", "customer_id",
                       "customer_id INTEGER REFERENCES customers(id)")
        _ensure_column(conn, "sales", "payment_status",
                       "payment_status VARCHAR(20) DEFAULT 'PAID'")
        _ensure_column(conn, "sales", "refundable",
                       "refundable BOOLEAN DEFAULT 1")
        _ensure_column(conn, "purchase_orders", "payment_status",
                       "payment_status VARCHAR(20) DEFAULT 'PAID'")


def _ensure_column(conn, table, column, ddl):
    existing = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")


# --------------------------------------------------------------------------- #
# Backups                                                                      #
# --------------------------------------------------------------------------- #
BACKUP_DIR_ENV = "STOCK_BACKUP_DIR"
DEFAULT_KEEP_BACKUPS = 10


def _db_file_path():
    """Absolute path of the SQLite database file (or None for :memory:)."""
    url_db = engine.url.database
    if not url_db or url_db == ":memory:":
        return None
    return os.path.abspath(url_db)


def backup_database(keep: int = DEFAULT_KEEP_BACKUPS) -> dict | None:
    """Create a consistent local snapshot of the SQLite database.

    The copy is produced via the SQLite online-backup API (safe even if the
    app is currently connected / mid-transaction). old backups are pruned so
    only the newest ``keep`` snapshots remain. Returns a dict with the saved
    path / directory, or None when the database is not a file (e.g. :memory:).
    """
    db_path = _db_file_path()
    if not db_path or not os.path.exists(db_path):
        return None

    backup_dir = os.environ.get(BACKUP_DIR_ENV) or os.path.join(
        os.path.dirname(db_path), "backups"
    )
    os.makedirs(backup_dir, exist_ok=True)

    dest_path = os.path.join(
        backup_dir, f"stock_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    )

    src = None
    dst = None
    try:
        src = engine.raw_connection()  # sqlite3.Connection
        dst = sqlite3.connect(dest_path)
        src.backup(dst)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()

    pattern = os.path.join(backup_dir, "stock_*.db")
    snapshots = sorted(glob.glob(pattern))
    for old in snapshots[:-keep]:
        try:
            os.remove(old)
        except OSError:
            pass

    return {
        "path": dest_path,
        "dir": backup_dir,
        "created": datetime.now(),
        "kept": min(keep, len(snapshots)),
        "total": len(snapshots),
    }