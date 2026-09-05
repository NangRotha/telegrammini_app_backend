import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, Order, OrderItem, Product, User, PromoCode
from app.schemas import OrderCreate, OrderResponse, OrderUpdateStatus
from app.telegram_service import (
    send_order_confirmation,
    send_admin_order_alert,
    send_order_status_update,
)
from app.websocket_manager import ws_manager
from app.services.khqr_service import create_khqr_payment

router = APIRouter(prefix="/orders", tags=["Orders"])


def generate_order_number() -> str:
    timestamp_part = datetime.now().strftime("%y%m%d")
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"MS-{timestamp_part}-{unique_part}"


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, db: AsyncSession = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    # Fetch products and verify availability
    product_ids = [item.product_id for item in payload.items]
    result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
    db_products = {p.id: p for p in result.scalars().all()}

    subtotal_amount = 0.0
    order_items_to_create = []

    for item in payload.items:
        prod = db_products.get(item.product_id)
        if not prod:
            raise HTTPException(status_code=404, detail=f"Product ID {item.product_id} not found")
        if not prod.is_active:
            raise HTTPException(status_code=400, detail=f"Product '{prod.title}' is no longer available")

        subtotal = round(prod.price * item.quantity, 2)
        subtotal_amount += subtotal

        # Decrease stock if available
        if prod.stock >= item.quantity:
            prod.stock -= item.quantity

        order_items_to_create.append(
            OrderItem(
                product_id=prod.id,
                product_title=prod.title,
                price=prod.price,
                quantity=item.quantity,
                subtotal=subtotal,
            )
        )

    # Upsert user if telegram_id is provided
    user = None
    if payload.telegram_id:
        user_res = await db.execute(select(User).where(User.id == payload.telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            user = User(
                id=payload.telegram_id,
                username=payload.username,
                first_name=payload.customer_name,
                phone=payload.customer_phone,
                points=0,
            )
            db.add(user)
        else:
            if payload.username:
                user.username = payload.username
            if payload.customer_phone:
                user.phone = payload.customer_phone

    # Calculate Promo Code Discount
    discount_amount = 0.0
    applied_promo = payload.promocode.strip().upper() if payload.promocode else ""
    if applied_promo:
        promo_res = await db.execute(
            select(PromoCode).where(PromoCode.code == applied_promo, PromoCode.is_active == True)
        )
        promo = promo_res.scalar_one_or_none()
        if promo and subtotal_amount >= promo.min_spend:
            if promo.discount_type == "percentage":
                disc = (subtotal_amount * promo.discount_value) / 100.0
                if promo.max_discount:
                    disc = min(disc, promo.max_discount)
            else:
                disc = promo.discount_value
            discount_amount += round(min(disc, subtotal_amount), 2)

    # Points redemption (100 pts = $1.00)
    points_redeemed = max(0, payload.points_redeemed or 0)
    if points_redeemed > 0 and user:
        if user.points >= points_redeemed:
            points_val = round(points_redeemed / 100.0, 2)
            usable_pts_disc = min(points_val, max(0.0, subtotal_amount - discount_amount))
            discount_amount += usable_pts_disc
            user.points = max(0, user.points - points_redeemed)
        else:
            points_redeemed = 0

    final_total = max(0.0, round(subtotal_amount - discount_amount, 2))
    points_earned = int(final_total * 10)  # 10 points per dollar spent
    if user:
        user.points += points_earned

    order_num = generate_order_number()
    payment_method = payload.payment_method or "cod"
    khqr_url = ""
    khqr_string = ""
    khqr_md5 = ""

    if payment_method == "khqr" and final_total > 0:
        try:
            khqr_res = await create_khqr_payment(
                transaction_id=order_num,
                amount=final_total,
                remark=f"Order #{order_num}",
            )
            khqr_url = khqr_res.get("qr_url", "")
            khqr_string = khqr_res.get("qr", "")
            khqr_md5 = khqr_res.get("md5", "")
        except Exception as e:
            print(f"KHQR generation warning: {e}")

    order = Order(
        order_number=order_num,
        user_id=payload.telegram_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        delivery_address=payload.delivery_address,
        total_amount=final_total,
        discount_amount=round(discount_amount, 2),
        promocode=applied_promo,
        points_redeemed=points_redeemed,
        points_earned=points_earned,
        status="pending",
        payment_method=payment_method,
        payment_status="unpaid",
        khqr_url=khqr_url,
        khqr_string=khqr_string,
        khqr_md5=khqr_md5,
        notes=payload.notes or "",
        items=order_items_to_create,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    # Load items relation
    order_query = select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    full_order = (await db.execute(order_query)).scalar_one()

    # Trigger Telegram notifications asynchronously
    try:
        await send_order_confirmation(full_order, full_order.items)
        await send_admin_order_alert(full_order, full_order.items)
    except Exception as e:
        # Logging only, don't fail the order creation
        print(f"Telegram alert trigger warning: {e}")

    # Broadcast real-time order creation and inventory update
    try:
        await ws_manager.broadcast("ORDER_CREATED", {
            "id": full_order.id,
            "order_number": full_order.order_number,
            "customer_name": full_order.customer_name,
            "customer_phone": full_order.customer_phone,
            "total_amount": full_order.total_amount,
            "status": full_order.status,
            "payment_method": full_order.payment_method,
            "payment_status": full_order.payment_status,
            "user_id": full_order.user_id,
            "created_at": full_order.created_at.isoformat() if full_order.created_at else None,
        })
        await ws_manager.broadcast("PRODUCT_UPDATED", {"reason": "stock_decrease"})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return full_order


@router.get("", response_model=List[OrderResponse])
async def list_all_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).options(selectinload(Order.items))
    if status_filter:
        query = query.where(Order.status == status_filter)
    query = query.order_by(Order.id.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/user/{telegram_id}", response_model=List[OrderResponse])
async def list_user_orders(telegram_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == telegram_id)
        .order_by(Order.id.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: int,
    payload: OrderUpdateStatus,
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    payment_changed_to_paid = False
    if payload.payment_status:
        if order.payment_status != "paid" and payload.payment_status == "paid":
            payment_changed_to_paid = True
        order.payment_status = payload.payment_status

    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)

    if payment_changed_to_paid:
        try:
            await ws_manager.broadcast("PAYMENT_CONFIRMED", {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": "paid",
                "amount": order.total_amount,
            })
        except Exception as ws_p_err:
            print(f"Payment confirmed broadcast warning: {ws_p_err}")

    if payload.notify_customer and order.user_id:
        try:
            await send_order_status_update(order, payload.status, payload.custom_message)
        except Exception as e:
            print(f"Failed to send customer status update: {e}")

    # Broadcast real-time order status update to customer and admin
    try:
        await ws_manager.broadcast("ORDER_STATUS_UPDATED", {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "user_id": order.user_id,
            "custom_message": payload.custom_message,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        })
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return order
