#!/usr/bin/python3

"""
SeekSpider - Seek.com.au Job Scraper
Run via the run.sh or run.ps1 script
"""

#!/usr/bin/python3

from plombery import get_app
from src import seek_spider_pipeline  # noqa: F401


def create_app():
    return get_app()


if __name__ == "__main__":
    import os
    import uvicorn

    in_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
    host = "0.0.0.0" if in_docker else "127.0.0.1"

    uvicorn.run(
        "app:create_app",
        host=host,
        port=8000,
        reload=True,
        factory=True,
        reload_dirs="..",
    )