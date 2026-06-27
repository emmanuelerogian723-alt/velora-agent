"""
Velora — Entry Point
Run with: python -m velora.main  OR  uvicorn velora.api.server:app
"""
import uvicorn
from velora.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "velora.api.server:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG,
    )
