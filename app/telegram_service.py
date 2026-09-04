import os
import hmac
import hashlib
import urllib.parse
import json
import logging
import asyncio
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("telegram_service")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8704943227:AAEQz0QRoeSRuZLU-DtYg7o6XRDuOIWIBjA")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "8401599473"))
MINI_APP_URL = os.getenv("MINI_APP_URL", "http://localhost:5173")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def validate_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256.
    Returns parsed user dict if valid, or None if invalid.
    """
    if not init_data or not BOT_TOKEN:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Secret key: HMAC-SHA-256 of token with key "WebAppData"
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if hmac.compare_digest(computed_hash, received_hash):
            user_data = parsed.get("user")
            return json.loads(user_data) if user_data else parsed
        return None
    except Exception as e:
        logger.error(f"Error validating initData: {e}")
        return None


async def send_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "HTML"
) -> bool:
    """Send a message to a Telegram chat via HTTP Bot API."""
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"Telegram API warning to {chat_id}: {data.get('description')}")
            return bool(data.get("ok"))
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")
        return False


async def setup_bot_menu_button(web_app_url: Optional[str] = None) -> bool:
    """Configures the chat menu button to launch the Mini App directly (Telegram requires HTTPS)."""
    global MINI_APP_URL
    target_url = web_app_url or os.getenv("MINI_APP_URL") or MINI_APP_URL
    if not target_url.startswith("https://"):
        logger.info(f"Skipping setChatMenuButton because Telegram requires an HTTPS URL (current: {target_url}). Set an HTTPS tunnel/domain URL in .env or via /api/bot/setup-menu.")
        return False

    MINI_APP_URL = target_url
    url = f"{TELEGRAM_API_BASE}/setChatMenuButton"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": "🛍 Open Shop",
            "web_app": {"url": target_url}
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            logger.info(f"Set Menu Button result: {data}")
            return bool(data.get("ok"))
    except Exception as e:
        logger.error(f"Failed to setChatMenuButton: {e}")
        return False


async def send_order_confirmation(order, items) -> bool:
    """Sends order receipt to the customer on Telegram."""
    if not order.user_id:
        return False

    items_list_html = "\n".join(
        f"• <b>{item.product_title}</b> x{item.quantity} — <i>${item.subtotal:.2f}</i>"
        for item in items
    )

    message = (
        f"🎉 <b>Thank you for your order, {order.customer_name}!</b>\n\n"
        f"📋 <b>Order Number:</b> <code>{order.order_number}</code>\n"
        f"📦 <b>Status:</b> 🟡 <i>{order.status.capitalize()}</i>\n\n"
        f"🛒 <b>Items:</b>\n{items_list_html}\n\n"
        f"💵 <b>Total Amount:</b> <b>${order.total_amount:.2f}</b>\n"
        f"📍 <b>Delivery Address:</b> {order.delivery_address}\n"
        f"📞 <b>Phone:</b> {order.customer_phone}\n\n"
        f"We will notify you here once your order is confirmed and on its way!"
    )

    markup = None
    if MINI_APP_URL.startswith("https://"):
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🛍 View in Mini App", "web_app": {"url": MINI_APP_URL}}
                ]
            ]
        }

    return await send_telegram_message(order.user_id, message, reply_markup=markup)


async def send_admin_order_alert(order, items) -> bool:
    """Sends instant alert to Store Admin (Rotha)."""
    items_list = "\n".join(
        f"  • {item.product_title} x{item.quantity} (${item.subtotal:.2f})"
        for item in items
    )

    message = (
        f"🚨 <b>NEW ORDER RECEIVED!</b> 🚨\n\n"
        f"<b>Order #:</b> <code>{order.order_number}</code>\n"
        f"<b>Customer:</b> {order.customer_name} (ID: <code>{order.user_id}</code>)\n"
        f"<b>Phone:</b> {order.customer_phone}\n"
        f"<b>Address:</b> {order.delivery_address}\n"
        f"<b>Notes:</b> {order.notes or 'None'}\n\n"
        f"<b>Ordered Items:</b>\n{items_list}\n\n"
        f"💰 <b>Total: ${order.total_amount:.2f}</b>"
    )

    return await send_telegram_message(ADMIN_TELEGRAM_ID, message)


async def send_order_status_update(order, new_status: str, custom_note: Optional[str] = None) -> bool:
    """Sends notification to customer when order status changes."""
    if not order.user_id:
        return False

    status_emojis = {
        "pending": "⏳ Pending",
        "confirmed": "✅ Confirmed & Being Prepared",
        "shipped": "🚚 Out for Delivery / Shipped",
        "delivered": "🎉 Delivered",
        "cancelled": "❌ Cancelled"
    }
    status_text = status_emojis.get(new_status, new_status.capitalize())

    message = (
        f"🔔 <b>Order Update</b>\n\n"
        f"Order <code>{order.order_number}</code> status has changed:\n"
        f"<b>Current Status:</b> {status_text}\n\n"
    )
    if custom_note:
        message += f"💬 <b>Note from store:</b> {custom_note}\n\n"

    message += "Thank you for shopping with us!"

    markup = None
    if MINI_APP_URL.startswith("https://"):
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🛍 Open Mini App", "web_app": {"url": MINI_APP_URL}}
                ]
            ]
        }

    return await send_telegram_message(order.user_id, message, reply_markup=markup)


async def run_bot_polling():
    """Background polling task to respond to Telegram user commands like /start."""
    offset = 0
    logger.info("Starting Telegram Bot long-polling loop...")

    # Set up menu button on boot (if HTTPS)
    await setup_bot_menu_button()

    while True:
        try:
            url = f"{TELEGRAM_API_BASE}/getUpdates"
            params = {"offset": offset, "timeout": 20}
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        message = update.get("message")
                        if not message:
                            continue

                        chat_id = message["chat"]["id"]
                        text = message.get("text", "")
                        first_name = message.get("from", {}).get("first_name", "Shopper")

                        if text.startswith("/start"):
                            welcome_text = (
                                f"👋 <b>Hello, {first_name}!</b>\n\n"
                                f"Welcome to <b>Mini Shop</b>! 🛍✨\n"
                                f"Explore our exclusive catalog, add items to your cart, "
                                f"and checkout seamlessly right inside Telegram!\n\n"
                            )
                            markup = None
                            if MINI_APP_URL.startswith("https://"):
                                welcome_text += "👇 <i>Tap the button below to launch the store:</i>"
                                markup = {
                                    "inline_keyboard": [
                                        [
                                            {"text": "🛍 Open Mini Shop", "web_app": {"url": MINI_APP_URL}}
                                        ]
                                    ]
                                }
                            else:
                                welcome_text += (
                                    f"Store link: {MINI_APP_URL}\n\n"
                                    f"<i>(Tip: To enable the native in-app WebApp button, set an HTTPS domain or tunnel URL in backend/.env)</i>"
                                )

                            await send_telegram_message(chat_id, welcome_text, reply_markup=markup)
        except asyncio.CancelledError:
            logger.info("Bot polling cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in bot polling: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(1)
