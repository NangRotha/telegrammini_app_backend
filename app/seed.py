import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db, Category, Product

SEED_CATEGORIES = [
    {"name": "Tech & Gadgets", "slug": "tech-gadgets", "icon": "🎧"},
    {"name": "Apparel & Style", "slug": "apparel", "icon": "👕"},
    {"name": "Specialty Coffee", "slug": "coffee", "icon": "☕"},
    {"name": "Everyday Carry", "slug": "edc", "icon": "🎒"},
]

SEED_PRODUCTS = [
    {
        "title": "AeroPro Wireless ANC Headphones",
        "description": "Studio-grade audio with hybrid Active Noise Cancellation, 40-hour battery life, and ultra-soft memory foam ear cushions.",
        "price": 189.99,
        "category_slug": "tech-gadgets",
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80",
        "stock": 35,
        "is_active": True,
        "is_featured": True,
    },
    {
        "title": "Tactile Mechanical Keyboard 75%",
        "description": "Hot-swappable custom lubricated switches, sound-dampening silicone gasket mount, and per-key RGB backlighting.",
        "price": 129.50,
        "category_slug": "tech-gadgets",
        "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=800&auto=format&fit=crop&q=80",
        "stock": 20,
        "is_active": True,
        "is_featured": True,
    },
    {
        "title": "MagMagnetic Slim 10000mAh Power Bank",
        "description": "Fast 15W wireless magnetic charging for iPhone & Android, compact aluminum chassis with LED battery indicator.",
        "price": 49.00,
        "category_slug": "tech-gadgets",
        "image_url": "https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=800&auto=format&fit=crop&q=80",
        "stock": 60,
        "is_active": True,
        "is_featured": False,
    },
    {
        "title": "Heavyweight French Terry Hoodie - Charcoal",
        "description": "Crafted from 480 GSM organic cotton with double-layered hood, dropped shoulders, and relaxed modern silhouette.",
        "price": 85.00,
        "category_slug": "apparel",
        "image_url": "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=800&auto=format&fit=crop&q=80",
        "stock": 45,
        "is_active": True,
        "is_featured": True,
    },
    {
        "title": "Acid-Wash Graphic Tee 'Future Tokyo'",
        "description": "Pre-shrunk 100% vintage cotton tee featuring high-density screenprinted retro cyberpunk graphic on back.",
        "price": 38.00,
        "category_slug": "apparel",
        "image_url": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=800&auto=format&fit=crop&q=80",
        "stock": 50,
        "is_active": True,
        "is_featured": False,
    },
    {
        "title": "Ethiopia Yirgacheffe Natural Whole Beans (250g)",
        "description": "Single-origin specialty roast with tasting notes of wild blueberry, bergamot, and delicate honey florals.",
        "price": 22.50,
        "category_slug": "coffee",
        "image_url": "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?w=800&auto=format&fit=crop&q=80",
        "stock": 40,
        "is_active": True,
        "is_featured": True,
    },
    {
        "title": "Ceramic Matte Pour-Over Dripper & Carafe",
        "description": "Handcrafted heat-retaining ceramic dripper engineered for 60-degree extraction with 500ml borosilicate server.",
        "price": 44.00,
        "category_slug": "coffee",
        "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=800&auto=format&fit=crop&q=80",
        "stock": 25,
        "is_active": True,
        "is_featured": False,
    },
    {
        "title": "All-Weather Crossbody Sling Bag 4L",
        "description": "Waterproof X-Pac fabric, Fidlock magnetic buckle, waterproof YKK zippers, and padded tablet compartment.",
        "price": 68.00,
        "category_slug": "edc",
        "image_url": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800&auto=format&fit=crop&q=80",
        "stock": 30,
        "is_active": True,
        "is_featured": True,
    },
    {
        "title": "Full-Grain Italian Leather Cardholder",
        "description": "Minimalist front-pocket wallet holding up to 8 cards and folded cash. RFID-blocking lining.",
        "price": 34.00,
        "category_slug": "edc",
        "image_url": "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800&auto=format&fit=crop&q=80",
        "stock": 55,
        "is_active": True,
        "is_featured": False,
    },
]


async def seed_data():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Check if products already exist
        existing = await db.execute(select(Product))
        if existing.scalars().first():
            print("Database already contains data, skipping seed.")
            return

        print("Seeding categories...")
        cat_map = {}
        for cat_data in SEED_CATEGORIES:
            cat = Category(**cat_data)
            db.add(cat)
            await db.commit()
            await db.refresh(cat)
            cat_map[cat.slug] = cat.id

        print("Seeding products...")
        for p_data in SEED_PRODUCTS:
            category_slug = p_data.pop("category_slug")
            cat_id = cat_map.get(category_slug)
            prod = Product(**p_data, category_id=cat_id)
            db.add(prod)

        await db.commit()
        print("Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_data())
