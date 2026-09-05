from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.database import get_db, Category, Product
from app.schemas import CategoryResponse, CategoryCreate, CategoryUpdate
from app.websocket_manager import ws_manager

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=List[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List all categories with live product count."""
    stmt = (
        select(Category, func.count(Product.id).label("product_count"))
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.id.asc())
    )
    result = await db.execute(stmt)
    categories = []
    for cat, p_count in result.all():
        cat.product_count = p_count or 0
        categories.append(cat)
    return categories


@router.get("/{cat_id}", response_model=CategoryResponse)
async def get_category(cat_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch single category by ID with product count."""
    stmt = (
        select(Category, func.count(Product.id).label("product_count"))
        .outerjoin(Product, Product.category_id == Category.id)
        .where(Category.id == cat_id)
        .group_by(Category.id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    cat, p_count = row
    cat.product_count = p_count or 0
    return cat


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    """Create a new category."""
    clean_slug = payload.slug.strip().lower()
    existing = await db.execute(select(Category).where(Category.slug == clean_slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Category slug '{clean_slug}' already exists")

    data = payload.model_dump()
    data["slug"] = clean_slug
    cat = Category(**data)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    cat.product_count = 0

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "create", "category_id": cat.id, "name": cat.name})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return cat


@router.put("/{cat_id}", response_model=CategoryResponse)
async def update_category(cat_id: int, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    """Update category details (name, slug, icon)."""
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"]:
        clean_slug = update_data["slug"].strip().lower()
        if clean_slug != cat.slug:
            existing = await db.execute(
                select(Category).where(Category.slug == clean_slug, Category.id != cat_id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail=f"Category slug '{clean_slug}' is already in use")
            update_data["slug"] = clean_slug

    for field, val in update_data.items():
        setattr(cat, field, val)

    await db.commit()
    await db.refresh(cat)

    p_count = await db.scalar(
        select(func.count(Product.id)).where(Product.category_id == cat.id)
    )
    cat.product_count = p_count or 0

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "update", "category_id": cat.id, "name": cat.name})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return cat


@router.delete("/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db)):
    """Delete category and safely unassign its products (sets product category_id to NULL)."""
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Safely detach products so they aren't deleted
    await db.execute(
        update(Product).where(Product.category_id == cat_id).values(category_id=None)
    )

    await db.delete(cat)
    await db.commit()

    try:
        await ws_manager.broadcast("CATEGORY_UPDATED", {"action": "delete", "category_id": cat_id})
    except Exception as ws_err:
        print(f"WebSocket broadcast warning: {ws_err}")

    return None
