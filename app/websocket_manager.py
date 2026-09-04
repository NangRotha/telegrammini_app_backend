import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Any = None):
        """
        Broadcasts a typed real-time event to all connected clients.
        Example event_types:
          - ORDER_CREATED
          - ORDER_STATUS_UPDATED
          - PRODUCT_UPDATED
          - CATEGORY_UPDATED
          - PROFILE_UPDATED
        """
        payload = {
            "type": event_type,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(payload))
            except Exception as e:
                logger.warning(f"Error sending message to client: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Global singleton instance for the app
ws_manager = ConnectionManager()
