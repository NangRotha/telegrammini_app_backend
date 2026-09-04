from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, PromoCode
from app.schemas import (
    PromoCodeResponse,
    PromoCodeCreate,
    PromoCodeUpdate,
    PromoCodeValidateRequest,
    PromoCodeValidateResponse,
)

router = APIRouter(prefix="/promocodes", tags=["PromoCodes"])


@router.get("", response_model=List[PromoCodeResponse])
async def list_promocodes(
    active_only: bool = Query(False, description="Filter only active promo codes"),
    db: AsyncSession = Depends(get_db),
):
    """List promo codes (all for admin, or active_only for client)."""
    query = select(PromoCode)
    if active_only:
        query = query.where(PromoCode.is_active == True)
    query = query.order_by(PromoCode.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_promocode(
    payload: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new promotional discount code."""
    code_clean = payload.code.strip().upper()
    existing = await db.execute(select(PromoCode).where(PromoCode.code == code_clean))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Promo code '{code_clean}' already exists.",
        )

    promocode = PromoCode(
        code=code_clean,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        min_spend=payload.min_spend,
        max_discount=payload.max_discount,
        description=payload.description or "",
        is_active=payload.is_active,
    )
    db.add(promocode)
    await db.commit()
    await db.refresh(promocode)
    return promocode


@router.put("/{promocode_id}", response_model=PromoCodeResponse)
async def update_promocode(
    promocode_id: int,
    payload: PromoCodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing promotional discount code."""
    promocode = await db.get(PromoCode, promocode_id)
    if not promocode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo code not found")

    if payload.code is not None:
        code_clean = payload.code.strip().upper()
        if code_clean != promocode.code:
            existing = await db.execute(select(PromoCode).where(PromoCode.code == code_clean))
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Promo code '{code_clean}' already exists.",
                )
            promocode.code = code_clean

    if payload.discount_type is not None:
        promocode.discount_type = payload.discount_type
    if payload.discount_value is not None:
        promocode.discount_value = payload.discount_value
    if payload.min_spend is not None:
        promocode.min_spend = payload.min_spend
    if payload.max_discount is not None:
        promocode.max_discount = payload.max_discount
    if payload.description is not None:
        promocode.description = payload.description
    if payload.is_active is not None:
        promocode.is_active = payload.is_active

    await db.commit()
    await db.refresh(promocode)
    return promocode


@router.delete("/{promocode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promocode(
    promocode_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a promotional discount code."""
    promocode = await db.get(PromoCode, promocode_id)
    if not promocode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo code not found")

    await db.delete(promocode)
    await db.commit()
    return None


@router.post("/validate", response_model=PromoCodeValidateResponse)
async def validate_promocode(
    payload: PromoCodeValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a promo code and calculate discount amount."""
    code_clean = payload.code.strip().upper()
    result = await db.execute(
        select(PromoCode).where(
            PromoCode.code == code_clean,
            PromoCode.is_active == True,
        )
    )
    promocode = result.scalar_one_or_none()

    if not promocode:
        return PromoCodeValidateResponse(
            valid=False,
            code=code_clean,
            discount_type="none",
            discount_value=0.0,
            discount_amount=0.0,
            final_total=payload.subtotal,
            message="Invalid or expired promo code.",
        )

    if payload.subtotal < promocode.min_spend:
        return PromoCodeValidateResponse(
            valid=False,
            code=code_clean,
            discount_type=promocode.discount_type,
            discount_value=promocode.discount_value,
            discount_amount=0.0,
            final_total=payload.subtotal,
            message=f"Minimum order of ${promocode.min_spend:.2f} required to use {code_clean}.",
        )

    # Calculate discount
    if promocode.discount_type == "percentage":
        discount = (payload.subtotal * promocode.discount_value) / 100.0
        if promocode.max_discount and discount > promocode.max_discount:
            discount = promocode.max_discount
    else:  # fixed
        discount = promocode.discount_value

    discount = min(discount, payload.subtotal)
    discount = round(discount, 2)
    final_total = max(0.0, round(payload.subtotal - discount, 2))

    return PromoCodeValidateResponse(
        valid=True,
        code=code_clean,
        discount_type=promocode.discount_type,
        discount_value=promocode.discount_value,
        discount_amount=discount,
        final_total=final_total,
        message=f"Promo code {code_clean} applied! You save ${discount:.2f}.",
    )
