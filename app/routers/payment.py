from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, Order
from app.services.khqr_service import (
    create_khqr_payment,
    check_khqr_transaction_status,
    verify_webhook_hash,
    generate_aba_checkout_url,
    KHQR_SECRET_KEY,
)
from app.websocket_manager import ws_manager
from app.telegram_service import send_order_status_update, send_admin_order_alert

logger = logging.getLogger("app.payment")
router = APIRouter(prefix="/payment", tags=["Payment"])


@router.post("/generate/{order_number}")
async def generate_khqr_for_order(order_number: str, db: AsyncSession = Depends(get_db)):
    """
    Generate or retrieve dynamic KHQR / ABA Pay code for an order.
    """
    query = select(Order).where(Order.order_number == order_number)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    checkout_url = generate_aba_checkout_url(order.order_number, order.total_amount)

    if order.payment_status == "paid":
        return {
            "success": True,
            "order_number": order.order_number,
            "amount": order.total_amount,
            "paid": True,
            "payment_status": "paid",
            "qr": order.khqr_string,
            "qr_url": order.khqr_url,
            "checkout_url": checkout_url,
            "aba_deeplink": checkout_url,
            "merchant_name": "NANG ROTHA (ABA Bank)",
        }

    # If QR already generated and cached on order, return it
    if order.khqr_url and order.khqr_string:
        return {
            "success": True,
            "order_number": order.order_number,
            "amount": order.total_amount,
            "paid": False,
            "payment_status": order.payment_status,
            "qr": order.khqr_string,
            "qr_url": order.khqr_url,
            "md5": order.khqr_md5,
            "checkout_url": checkout_url,
            "aba_deeplink": checkout_url,
            "merchant_name": "NANG ROTHA (ABA Bank)",
        }

    # Generate new KHQR code via khqr.cc service
    khqr_res = await create_khqr_payment(
        transaction_id=order.order_number,
        amount=order.total_amount,
        remark=f"Order {order.order_number}",
    )

    order.khqr_url = khqr_res.get("qr_url", "")
    order.khqr_string = khqr_res.get("qr", "")
    order.khqr_md5 = khqr_res.get("md5", "")
    order.payment_method = "khqr"
    await db.commit()
    await db.refresh(order)

    return {
        "success": True,
        "order_number": order.order_number,
        "amount": order.total_amount,
        "paid": order.payment_status == "paid",
        "payment_status": order.payment_status,
        "qr": order.khqr_string,
        "qr_url": order.khqr_url,
        "md5": order.khqr_md5,
        "checkout_url": khqr_res.get("checkout_url", checkout_url),
        "aba_deeplink": khqr_res.get("aba_deeplink", checkout_url),
        "merchant_name": khqr_res.get("merchant_name", "NANG ROTHA (ABA Bank)"),
        "is_sandbox": khqr_res.get("is_sandbox", False),
    }


@router.get("/check/{order_number}")
async def check_order_payment_status(order_number: str, db: AsyncSession = Depends(get_db)):
    """
    Check if KHQR payment was completed for this order.
    Calls check-trans on khqr.cc and updates local DB if paid.
    """
    query = select(Order).options(selectinload(Order.items)).where(Order.order_number == order_number)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.payment_status == "paid":
        return {
            "paid": True,
            "status": "paid",
            "order_status": order.status,
            "order_number": order.order_number,
        }

    # Query gateway check-trans
    trans_check = await check_khqr_transaction_status(order.order_number)

    if trans_check.get("is_paid"):
        order.payment_status = "paid"
        if order.status == "pending":
            order.status = "confirmed"
        order.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(order)

        # Broadcast real-time payment confirmation to client & admin
        try:
            await ws_manager.broadcast("PAYMENT_CONFIRMED", {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": "paid",
                "amount": order.total_amount,
            })
            await ws_manager.broadcast("ORDER_STATUS_UPDATED", {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": "paid",
                "user_id": order.user_id,
                "custom_message": "Payment verified successfully via KHQR scan",
            })
        except Exception as ws_err:
            logger.warning(f"WebSocket broadcast error: {ws_err}")

        # Send Telegram notifications
        if order.user_id:
            try:
                await send_order_status_update(order, "confirmed", "✅ Payment received via KHQR! Your order is confirmed.")
            except Exception as e:
                logger.error(f"Failed to send Telegram payment confirmation: {e}")

        return {
            "paid": True,
            "status": "paid",
            "order_status": order.status,
            "order_number": order.order_number,
            "data": trans_check.get("data", {}),
        }

    return {
        "paid": False,
        "status": order.payment_status,
        "order_status": order.status,
        "order_number": order.order_number,
    }


@router.post("/callback")
async def payment_webhook_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receives automated HTTP POST webhook callbacks from khqr.cc gateway.
    Formula: sha256(secret + req_time + transaction_id + amount + "SUCCESS")
    Always returns HTTP 200 as requested by the gateway documentation.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("Invalid JSON payload received in payment callback")
        return {"received": True}

    logger.info(f"Received KHQR webhook callback: {body}")

    req_time = body.get("req_time", "")
    transaction_id = body.get("transaction_id") or body.get("order_ref") or body.get("order_id", "")
    amount = body.get("amount") or body.get("paid_usd") or body.get("paid_amount", "")
    status_str = body.get("status") or body.get("event", "SUCCESS")
    received_hash = body.get("hash") or body.get("signature", "")

    if not transaction_id:
        return {"received": True}

    # Verify SHA-256 signature
    is_valid = verify_webhook_hash(
        KHQR_SECRET_KEY,
        req_time,
        transaction_id,
        amount,
        status_str,
        received_hash
    )

    if not is_valid:
        logger.warning(f"Invalid webhook signature for order {transaction_id}")
        # Reject unauthorized requests if hash is explicitly forged
        # but return 200 or 403 based on configuration
        return Response(content='{"error": "Invalid signature"}', status_code=403, media_type="application/json")

    # Find and update order
    query = select(Order).options(selectinload(Order.items)).where(Order.order_number == transaction_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if order and order.payment_status != "paid":
        order.payment_status = "paid"
        if order.status == "pending":
            order.status = "confirmed"
        order.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(order)

        # Broadcast payment confirmation
        try:
            await ws_manager.broadcast("PAYMENT_CONFIRMED", {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": "paid",
                "amount": order.total_amount,
            })
            await ws_manager.broadcast("ORDER_STATUS_UPDATED", {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": "paid",
                "user_id": order.user_id,
                "custom_message": "Payment confirmed via KHQR Bakong scan",
            })
        except Exception as ws_err:
            logger.warning(f"WebSocket broadcast error: {ws_err}")

        # Send Telegram notification
        if order.user_id:
            try:
                await send_order_status_update(order, "confirmed", "✅ Payment received via KHQR! Your order is confirmed.")
            except Exception as e:
                logger.error(f"Failed to send Telegram payment confirmation: {e}")

    return {"received": True}


@router.post("/simulate-success/{order_number}")
async def simulate_payment_success(order_number: str, db: AsyncSession = Depends(get_db)):
    """
    Simulation / Test Endpoint:
    Instantly marks an order as paid & confirmed for quick testing and demonstrations.
    """
    query = select(Order).options(selectinload(Order.items)).where(Order.order_number == order_number)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.payment_status = "paid"
    order.payment_method = "khqr"
    if order.status == "pending":
        order.status = "confirmed"
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)

    # Broadcast real-time event
    try:
        await ws_manager.broadcast("PAYMENT_CONFIRMED", {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": "paid",
            "amount": order.total_amount,
        })
        await ws_manager.broadcast("ORDER_STATUS_UPDATED", {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": "paid",
            "user_id": order.user_id,
            "custom_message": "Payment verified (Simulation test)",
        })
    except Exception as ws_err:
        logger.warning(f"WebSocket broadcast error: {ws_err}")

    # Notify via Telegram
    if order.user_id:
        try:
            await send_order_status_update(order, "confirmed", "✅ Payment received via KHQR! Your order is confirmed.")
        except Exception as e:
            logger.error(f"Telegram notification warning: {e}")

    return {
        "success": True,
        "order_number": order.order_number,
        "status": order.status,
        "payment_status": order.payment_status,
    }
