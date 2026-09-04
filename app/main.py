import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import os
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.seed import seed_data
from app.telegram_service import run_bot_polling
from app.routers import categories, products, orders, stats, bot, users, upload, promocodes, payment
from app.websocket_manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and seed
    logger.info("Initializing database...")
    await init_db()
    logger.info("Checking & seeding initial catalog...")
    await seed_data()

    # Launch background Telegram Bot polling task
    logger.info("Starting Telegram Bot worker...")
    bot_task = asyncio.create_task(run_bot_polling())

    yield

    # Shutdown
    logger.info("Stopping Telegram Bot worker...")
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Mini Shop Telegram Bot API",
    description="Backend service for @minishopnuckbot Telegram Mini App and Admin Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from Vite dev servers, mobile webview, and production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount local PC uploads directory for images, videos, and avatars
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Include API Routers
app.include_router(categories.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(bot.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(promocodes.router, prefix="/api")
app.include_router(payment.router, prefix="/api")


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "PONG"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client closed: {e}")
        ws_manager.disconnect(websocket)


@app.get("/")
async def root():
    return {
        "service": "Mini Shop Telegram Mini App API",
        "status": "online",
        "bot": "@minishopnuckbot",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
