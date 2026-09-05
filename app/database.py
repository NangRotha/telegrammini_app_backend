import os
from datetime import datetime, timezone
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship

load_dotenv()

RAW_DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shop.db")

# Automatically adapt Render's postgres:// or postgresql:// to postgresql+asyncpg://
if RAW_DB_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif RAW_DB_URL.startswith("postgresql://") and not RAW_DB_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = RAW_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = RAW_DB_URL

is_sqlite = "sqlite" in DATABASE_URL
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    icon = Column(String(50), default="📦")

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    price = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(String(500), default="")
    sub_images = Column(Text, default="[]")
    video_url = Column(String(500), nullable=True, default="")
    stock = Column(Integer, default=50)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    category = relationship("Category", back_populates="products")


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)  # Telegram User ID
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    default_address = Column(Text, nullable=True, default="")
    avatar_url = Column(String(500), nullable=True, default="")
    points = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    orders = relationship("Order", back_populates="user")


class AlertPopup(Base):
    __tablename__ = "alert_popups"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False, default="")
    image_url = Column(String(500), nullable=True, default="")
    button_text = Column(String(50), nullable=True, default="Got It")
    button_link = Column(String(500), nullable=True, default="")
    popup_type = Column(String(50), default="promo")  # promo, announcement, info, warning
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class StoreSetting(Base):
    __tablename__ = "store_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=False, default="")


class PromoCode(Base):
    __tablename__ = "promocodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    discount_type = Column(String(20), default="percentage")  # "percentage" or "fixed"
    discount_value = Column(Float, nullable=False)
    min_spend = Column(Float, default=0.0)
    max_discount = Column(Float, nullable=True)
    description = Column(String(200), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_name = Column(String(150), nullable=False)
    customer_phone = Column(String(50), nullable=False)
    delivery_address = Column(Text, nullable=False)
    total_amount = Column(Float, nullable=False)
    discount_amount = Column(Float, default=0.0)
    promocode = Column(String(50), nullable=True, default="")
    points_redeemed = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)
    status = Column(String(50), default="pending", index=True)  # pending, confirmed, shipped, delivered, cancelled
    payment_method = Column(String(50), default="cod")  # "cod" or "khqr"
    payment_status = Column(String(50), default="unpaid")  # "unpaid" or "paid"
    khqr_url = Column(Text, default="")
    khqr_string = Column(Text, default="")
    khqr_md5 = Column(String(100), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, nullable=True)
    product_title = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)
    subtotal = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Check and migrate columns in SQLite if not present
        def check_and_migrate(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            
            # Users table columns
            user_cols = [c["name"] for c in inspector.get_columns("users")]
            is_postgres = connection.dialect.name == "postgresql"
            dt_col_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "DATETIME"
            if "default_address" not in user_cols:
                connection.execute(text("ALTER TABLE users ADD COLUMN default_address TEXT DEFAULT ''"))
            if "updated_at" not in user_cols:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN updated_at {dt_col_type}"))
            if "avatar_url" not in user_cols:
                connection.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''"))
            if "points" not in user_cols:
                connection.execute(text("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0"))

            # Products table columns
            prod_cols = [c["name"] for c in inspector.get_columns("products")]
            if "video_url" not in prod_cols:
                connection.execute(text("ALTER TABLE products ADD COLUMN video_url TEXT DEFAULT ''"))

            # Orders table columns
            order_cols = [c["name"] for c in inspector.get_columns("orders")]
            if "discount_amount" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN discount_amount REAL DEFAULT 0.0"))
            if "promocode" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN promocode TEXT DEFAULT ''"))
            if "points_redeemed" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN points_redeemed INTEGER DEFAULT 0"))
            if "points_earned" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN points_earned INTEGER DEFAULT 0"))
            if "payment_method" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN payment_method VARCHAR(50) DEFAULT 'cod'"))
            if "payment_status" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN payment_status VARCHAR(50) DEFAULT 'unpaid'"))
            if "khqr_url" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN khqr_url TEXT DEFAULT ''"))
            if "khqr_string" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN khqr_string TEXT DEFAULT ''"))
            if "khqr_md5" not in order_cols:
                connection.execute(text("ALTER TABLE orders ADD COLUMN khqr_md5 VARCHAR(100) DEFAULT ''"))

            # Default promo codes
            existing_codes = [r[0] for r in connection.execute(text("SELECT code FROM promocodes")).fetchall()]
            default_promos = [
                ("WELCOME10", "percentage", 10.0, 0.0, 50.0, "10% off entire order for all new shoppers"),
                ("SAVE20", "percentage", 20.0, 50.0, 100.0, "20% off on orders over $50"),
                ("MINI5", "fixed", 5.0, 20.0, 5.0, "$5 off on orders over $20"),
                ("VIP50", "percentage", 50.0, 100.0, 150.0, "VIP exclusive 50% discount on orders over $100"),
            ]
            for code, dtype, val, min_sp, max_d, desc in default_promos:
                if code not in existing_codes:
                    connection.execute(text(
                        "INSERT INTO promocodes (code, discount_type, discount_value, min_spend, max_discount, description, is_active) "
                        "VALUES (:code, :dtype, :val, :min_sp, :max_d, :desc, 1)"
                    ), {"code": code, "dtype": dtype, "val": val, "min_sp": min_sp, "max_d": max_d, "desc": desc})

            # Default Store Settings (Name, Logo, Password)
            existing_settings = [r[0] for r in connection.execute(text("SELECT key FROM store_settings")).fetchall()]
            default_settings = [
                ("store_name", "Mini Shop"),
                ("store_logo", "🛍"),
                ("store_tagline", "Store Admin"),
                ("admin_username", "admin"),
                ("admin_password_hash", "08d021dd0ab454eeba0dff703700d9c01d50da684f52853534d3b89e10c487a5"),  # admin123
            ]
            for k, v in default_settings:
                if k not in existing_settings:
                    connection.execute(
                        text("INSERT INTO store_settings (key, value) VALUES (:key, :value)"),
                        {"key": k, "value": v}
                    )

        await conn.run_sync(check_and_migrate)
