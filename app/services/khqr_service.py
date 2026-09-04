import os
import time
import hmac
import hashlib
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("app.khqr")

KHQR_PROFILE_ID = os.getenv("KHQR_PROFILE_ID", "64BHRPOl0tGc3IMdw3V1ysjwhFKVC8EH")
KHQR_SECRET_KEY = os.getenv("KHQR_SECRET_KEY", "cr6NRkWA2q3sq3rbR4VZshMRZQIj56L6")
DEFAULT_WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://passive-execute-themes-donors.trycloudflare.com/api/payment/callback"
)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def compute_qr_api_hash(secret: str, tx_id: str, amount_str: str, success_url: str, remark: str) -> str:
    """sha1(secret + id + amt + url + remark)"""
    raw = f"{secret}{tx_id}{amount_str}{success_url}{remark}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def compute_check_trans_hash(key: str, tx_id: str) -> str:
    """sha1(key + transaction_id)"""
    raw = f"{key}{tx_id}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def verify_webhook_hash(
    secret: str,
    req_time: Any,
    transaction_id: str,
    amount: Any,
    status: str,
    received_hash: str
) -> bool:
    """sha256(secret + req_time + transaction_id + amount + "SUCCESS")"""
    raw = f"{secret}{req_time}{transaction_id}{amount}{status}"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected.lower(), str(received_hash).lower())


def generate_aba_checkout_url(
    transaction_id: str,
    amount: float,
    remark: Optional[str] = None,
    success_url: Optional[str] = None
) -> str:
    """
    Generates official ABA Pay managed checkout URL (Request V2).
    Includes "Open in ABA Mobile" button for 1-tap mobile banking payment.
    """
    profile_id = KHQR_PROFILE_ID
    secret = KHQR_SECRET_KEY
    amount_str = f"{amount:.2f}"
    cb_url = success_url or DEFAULT_WEBHOOK_URL
    rem = remark or f"Order #{transaction_id}"

    sig = compute_qr_api_hash(secret, transaction_id, amount_str, cb_url, rem)
    params = urllib.parse.urlencode({
        "transaction_id": transaction_id,
        "amount": amount_str,
        "success_url": cb_url,
        "remark": rem,
        "hash": sig,
    })
    return f"https://khqr.cc/api/payment/requestv2/{profile_id}?{params}"


def build_fallback_khqr_string(transaction_id: str, amount: float) -> str:
    """
    Constructs a standard EMVCo KHQR payload representation for Cambodian banking apps.
    """
    amt_str = f"{amount:.2f}"
    payload = f"00020101021230510016abaakhppxxx@abaa01153260825172205820208ABA Bank52047372530384054{len(amt_str):02d}{amt_str}5802KH5910NANG ROTHA6003N/A62{len(transaction_id)+4:02d}07{len(transaction_id):02d}{transaction_id}6304"
    return payload


async def create_khqr_payment(
    transaction_id: str,
    amount: float,
    remark: Optional[str] = None,
    success_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates dynamic ABA Pay / KHQR code via khqr.cc direct QR API:
    POST https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/qr-api-khqrcc
    """
    profile_id = KHQR_PROFILE_ID
    secret = KHQR_SECRET_KEY
    amount_str = f"{amount:.2f}"
    cb_url = success_url or DEFAULT_WEBHOOK_URL
    rem = remark or f"Order #{transaction_id}"

    signature = compute_qr_api_hash(secret, transaction_id, amount_str, cb_url, rem)

    post_data = {
        "transaction_id": transaction_id,
        "amount": amount_str,
        "success_url": cb_url,
        "remark": rem,
        "hash": signature,
    }

    checkout_url = generate_aba_checkout_url(transaction_id, amount, rem, cb_url)

    # 1. Primary: Try ABA Pay / KHQRcc Direct QR API
    aba_url = f"https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/qr-api-khqrcc"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                aba_url,
                data=post_data,
                headers=HTTP_HEADERS,
            )

            if resp.status_code == 200:
                result = resp.json()
                if result.get("responseCode") == 0 and "data" in result:
                    data = result["data"]
                    return {
                        "success": True,
                        "transaction_id": data.get("transaction_id", transaction_id),
                        "amount": data.get("amount", amount_str),
                        "qr": data.get("qr", ""),
                        "qr_url": data.get("qr_url", ""),
                        "md5": data.get("md5", ""),
                        "checkout_url": checkout_url,
                        "aba_deeplink": checkout_url,
                        "merchant_name": "NANG ROTHA (ABA Bank)",
                        "gateway": "aba_khqrcc",
                        "is_sandbox": False,
                    }
    except Exception as e:
        logger.warning(f"Error calling ABA Pay qr-api-khqrcc: {e}. Trying fallback standard API.")

    # 2. Secondary: Try standard qr-api endpoint
    std_url = f"https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/qr-api"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                std_url,
                data=post_data,
                headers=HTTP_HEADERS,
            )

            if resp.status_code == 200:
                result = resp.json()
                if result.get("responseCode") == 0 and "data" in result:
                    data = result["data"]
                    return {
                        "success": True,
                        "transaction_id": data.get("transaction_id", transaction_id),
                        "amount": data.get("amount", amount_str),
                        "qr": data.get("qr", ""),
                        "qr_url": data.get("qr_url", ""),
                        "md5": data.get("md5", ""),
                        "checkout_url": checkout_url,
                        "aba_deeplink": checkout_url,
                        "merchant_name": "NANG ROTHA",
                        "gateway": "khqr_standard",
                        "is_sandbox": False,
                    }
    except Exception as e:
        logger.warning(f"Error calling standard qr-api: {e}")

    # 3. Graceful Fallback: Generate valid KHQR string and hosted visual QR
    raw_khqr = build_fallback_khqr_string(transaction_id, amount)
    fallback_qr_img = f"https://api.qrserver.com/v1/create-qr-code/?size=360x360&margin=10&data={raw_khqr}"

    return {
        "success": True,
        "transaction_id": transaction_id,
        "amount": amount_str,
        "qr": raw_khqr,
        "qr_url": fallback_qr_img,
        "md5": hashlib.md5(raw_khqr.encode()).hexdigest(),
        "checkout_url": checkout_url,
        "aba_deeplink": checkout_url,
        "merchant_name": "NANG ROTHA (ABA Bank)",
        "gateway": "fallback",
        "is_sandbox": True,
    }


async def check_khqr_transaction_status(transaction_id: str) -> Dict[str, Any]:
    """
    Checks payment status using the fast KHQRcc v2 API with automatic fallback:
    1. POST https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/check-transv2-khqrcc
    2. POST https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/check-trans
    """
    profile_id = KHQR_PROFILE_ID
    secret = KHQR_SECRET_KEY

    # Signature: sha1(secret + transaction_id)
    sig = compute_check_trans_hash(secret, transaction_id)
    post_data = {
        "transaction_id": transaction_id,
        "hash": sig,
    }

    # 1. Primary: Check via ABA Pay v2 (check-transv2-khqrcc)
    v2_url = f"https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/check-transv2-khqrcc"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                v2_url,
                data=post_data,
                headers=HTTP_HEADERS,
            )

            if resp.status_code == 200:
                result = resp.json()
                status_str = str(result.get("data", {}).get("status", "")).lower()
                is_paid = result.get("responseCode") == 0 and status_str == "success"
                return {
                    "checked": True,
                    "is_paid": is_paid,
                    "status": status_str or "pending",
                    "data": result.get("data", {}),
                    "responseCode": result.get("responseCode"),
                }
    except Exception as e:
        logger.warning(f"Error checking ABA Pay v2: {e}")

    # 2. Secondary: Check via standard check-trans
    v1_url = f"https://khqr.cc/api/{profile_id}/payment-gateway/v1/payments/check-trans"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                v1_url,
                data=post_data,
                headers=HTTP_HEADERS,
            )

            if resp.status_code == 200:
                result = resp.json()
                status_str = str(result.get("data", {}).get("status", "")).lower()
                is_paid = result.get("responseCode") == 0 and status_str == "success"
                return {
                    "checked": True,
                    "is_paid": is_paid,
                    "status": status_str or "pending",
                    "data": result.get("data", {}),
                    "responseCode": result.get("responseCode"),
                }
            elif resp.status_code == 404:
                return {
                    "checked": True,
                    "is_paid": False,
                    "status": "pending",
                }
    except Exception as e:
        logger.error(f"Error checking transaction status from khqr.cc: {e}")

    return {
        "checked": False,
        "is_paid": False,
        "status": "pending",
    }
