from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db, Order, Product
from app.schemas import StatsResponse, OrderResponse

router = APIRouter(prefix="/stats", tags=["Dashboard Stats"])


@router.get("", response_model=StatsResponse)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    # Total revenue from non-cancelled orders
    rev_query = select(func.coalesce(func.sum(Order.total_amount), 0.0)).where(Order.status != "cancelled")
    total_revenue = float((await db.execute(rev_query)).scalar_one())

    # Total orders
    orders_count_query = select(func.count(Order.id))
    total_orders = int((await db.execute(orders_count_query)).scalar_one())

    # Total products
    prods_count_query = select(func.count(Product.id))
    total_products = int((await db.execute(prods_count_query)).scalar_one())

    # Pending orders
    pending_query = select(func.count(Order.id)).where(Order.status == "pending")
    pending_orders = int((await db.execute(pending_query)).scalar_one())

    # Completed (delivered) orders
    completed_query = select(func.count(Order.id)).where(Order.status == "delivered")
    completed_orders = int((await db.execute(completed_query)).scalar_one())

    # Recent 5 orders
    recent_query = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.id.desc())
        .limit(5)
    )
    recent_orders = (await db.execute(recent_query)).scalars().all()

    return StatsResponse(
        total_revenue=round(total_revenue, 2),
        total_orders=total_orders,
        total_products=total_products,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        recent_orders=recent_orders,
    )
