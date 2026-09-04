import json
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


# Category Schemas
class CategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100)
    icon: Optional[str] = "📦"


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    icon: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# Product Schemas
class ProductBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = ""
    price: float = Field(..., gt=0)
    category_id: Optional[int] = None
    image_url: Optional[str] = ""
    sub_images: List[str] = Field(default_factory=list)
    video_url: Optional[str] = ""
    stock: int = Field(default=50, ge=0)
    is_active: bool = True
    is_featured: bool = False

    @classmethod
    def parse_sub_images_value(cls, v):
        if isinstance(v, str):
            try:
                import json
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return [v] if v.strip() else []
        elif isinstance(v, list):
            return [str(x) for x in v]
        return []


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    sub_images: Optional[List[str]] = None
    video_url: Optional[str] = None
    stock: Optional[int] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    created_at: Optional[datetime] = None
    category: Optional[CategoryResponse] = None
    sub_images: List[str] = Field(default_factory=list)
    video_url: Optional[str] = ""
    model_config = ConfigDict(from_attributes=True)

    @field_validator('sub_images', mode='before')
    @classmethod
    def parse_sub_images(cls, v):
        return ProductBase.parse_sub_images_value(v)


# Promo Code Schemas
class PromoCodeResponse(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: float
    min_spend: float
    max_discount: Optional[float] = None
    description: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class PromoCodeCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    discount_type: str = Field("percentage", pattern="^(percentage|fixed)$")
    discount_value: float = Field(..., gt=0)
    min_spend: float = Field(0.0, ge=0)
    max_discount: Optional[float] = Field(None, ge=0)
    description: Optional[str] = ""
    is_active: bool = True


class PromoCodeUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    discount_type: Optional[str] = Field(None, pattern="^(percentage|fixed)$")
    discount_value: Optional[float] = Field(None, gt=0)
    min_spend: Optional[float] = Field(None, ge=0)
    max_discount: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PromoCodeValidateRequest(BaseModel):
    code: str
    subtotal: float = Field(..., ge=0)


class PromoCodeValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str
    discount_value: float
    discount_amount: float
    final_total: float
    message: str


# Order Schemas
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class OrderItemResponse(BaseModel):
    id: int
    product_id: Optional[int]
    product_title: str
    price: float
    quantity: int
    subtotal: float
    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    customer_name: str
    customer_phone: str
    delivery_address: str
    notes: Optional[str] = ""
    promocode: Optional[str] = None
    points_redeemed: Optional[int] = 0
    payment_method: Optional[str] = "cod"
    items: List[OrderItemCreate]


class OrderUpdateStatus(BaseModel):
    status: str = Field(..., pattern="^(pending|confirmed|shipped|delivered|cancelled)$")
    payment_status: Optional[str] = Field(None, pattern="^(paid|unpaid|refunded)$")
    notify_customer: bool = True
    custom_message: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    order_number: str
    user_id: Optional[int]
    customer_name: str
    customer_phone: str
    delivery_address: str
    total_amount: float
    discount_amount: float = 0.0
    promocode: Optional[str] = ""
    points_redeemed: int = 0
    points_earned: int = 0
    status: str
    payment_method: Optional[str] = "cod"
    payment_status: Optional[str] = "unpaid"
    khqr_url: Optional[str] = ""
    khqr_string: Optional[str] = ""
    khqr_md5: Optional[str] = ""
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []
    model_config = ConfigDict(from_attributes=True)


# Dashboard Stats
class StatsResponse(BaseModel):
    total_revenue: float
    total_orders: int
    total_products: int
    pending_orders: int
    completed_orders: int
    recent_orders: List[OrderResponse] = []


# Bot Notification Request
class NotifyRequest(BaseModel):
    telegram_id: int
    message: str
    parse_mode: Optional[str] = "Markdown"


# User Profile Schemas
class UserResponse(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    default_address: Optional[str] = ""
    avatar_url: Optional[str] = ""
    points: int = 100
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    default_address: Optional[str] = None
    avatar_url: Optional[str] = None
    points: Optional[int] = None

