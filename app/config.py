import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.config")

# Base Upload Directory
# In Render with Persistent Disk: UPLOAD_DIR=/var/data/uploads (or mount at /var/data)
# In local development: defaults to backend/uploads
env_upload_dir = os.getenv("UPLOAD_DIR")

if env_upload_dir and env_upload_dir.strip():
    UPLOAD_DIR = os.path.abspath(env_upload_dir.strip())
elif os.path.exists("/var/data"):
    # Automatically detect Render persistent disk mounted at /var/data
    UPLOAD_DIR = "/var/data/uploads"
else:
    UPLOAD_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "uploads")
    )

# Subdirectories for media types
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
VIDEOS_DIR = os.path.join(UPLOAD_DIR, "videos")
AVATARS_DIR = os.path.join(UPLOAD_DIR, "avatars")


def ensure_upload_dirs():
    """Ensure upload root directory and all subdirectories exist."""
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(VIDEOS_DIR, exist_ok=True)
        os.makedirs(AVATARS_DIR, exist_ok=True)
        logger.info(f"Upload directories initialized successfully at: {UPLOAD_DIR}")
    except Exception as e:
        logger.error(f"Failed to create upload directories at {UPLOAD_DIR}: {e}")
