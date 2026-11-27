"""ASGI entry point used by uvicorn: ``uvicorn app.asgi:app``."""

from app.main import create_app

app = create_app()
