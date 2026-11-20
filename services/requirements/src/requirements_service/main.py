"""Точка входа ASGI-приложения uvicorn."""
from .api.app import create_app

app = create_app()
