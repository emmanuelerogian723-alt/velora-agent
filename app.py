"""
Velora — Render Entry Point
This file exists so Render can start Velora with:
  uvicorn app:app
Which avoids any Python package path issues.
"""
from api.server import app

__all__ = ["app"]
