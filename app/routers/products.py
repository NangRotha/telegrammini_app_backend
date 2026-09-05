import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, Product, Category
from app.schemas import ProductResponse, ProductCreate, ProductUpdate
from app.websocket_manager import ws_manager

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=List[ProductResponse])
async def list_products(
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    featured_only: Optional[bool] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).options(selectinload(Product.category))

    if active_only:
        query = query.where(Product.is_active == True)
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if featured_only is not None and featured_only:
        query = query.where(Product.is_featured == True)
    if search:
        search_pattern = f"%{search.lower()}%"
        query = query.where(Product.title.ilike(search_pattern) | Product.description.ilike(search_pattern))

    query = query.order_by(Product.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{prod_id}", response_model=ProductResponse)
async def get_product(prod_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Product).options(selectinload(Product.category)).where(Product.id == prod_id)
    result = await db.execute(query)
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    if payload.category_id:
        cat = await db.execute(select(Category).where(Category.id == payload.category_id))
        if not cat.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid category_id")

    data = payload.model_dump()
    if "sub_images" in data and isinstance(data["sub_images"], list):
        data["sub_images"] = json.dumps(data["sub_images"])

    prod = Product(**data)
    db.add(prod)
    await db.commit()
    await db.refresh(prod)
    # Reload with category
    query = select(Product).options(selectinload(Product.category)).where(Product.id == prod.id)
    result = await db.execute(query)
    saved_prod = result.scalar_one()

    try:
        prod_data = ProductResponse.model_validate(saved_prod).model_dump(mode="json")
        await ws_manager.broadcast("PRODUCT_UPDATED", {
            "action": "create",
            "product_id": saved_prod.id,
            "product": prod_data,
        })
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return saved_prod


@router.put("/{prod_id}", response_model=ProductResponse)
async def update_product(prod_id: int, payload: ProductUpdate, db: AsyncSession = Depends(get_db)):
    query = select(Product).options(selectinload(Product.category)).where(Product.id == prod_id)
    result = await db.execute(query)
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data and update_data["category_id"] is not None:
        cat = await db.execute(select(Category).where(Category.id == update_data["category_id"]))
        if not cat.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid category_id")

    if "sub_images" in update_data and isinstance(update_data["sub_images"], list):
        update_data["sub_images"] = json.dumps(update_data["sub_images"])

    for field, val in update_data.items():
        setattr(prod, field, val)

    await db.commit()
    await db.refresh(prod)

    # Reload with category for broadcast
    query = select(Product).options(selectinload(Product.category)).where(Product.id == prod.id)
    result = await db.execute(query)
    refreshed_prod = result.scalar_one()

    try:
        prod_data = ProductResponse.model_validate(refreshed_prod).model_dump(mode="json")
        await ws_manager.broadcast("PRODUCT_UPDATED", {
            "action": "update",
            "product_id": refreshed_prod.id,
            "product": prod_data,
        })
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return refreshed_prod


@router.delete("/{prod_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(prod_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == prod_id))
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(prod)
    await db.commit()

    try:
        await ws_manager.broadcast("PRODUCT_UPDATED", {
            "action": "delete",
            "product_id": prod_id,
        })
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return None
