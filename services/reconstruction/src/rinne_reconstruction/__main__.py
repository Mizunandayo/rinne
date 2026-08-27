"""Entrypoint"""

from __future__ import annotations

import uvicorn

from rinne_reconstruction.app import create_app
from rinne_reconstruction.config import get_settings


def main() -> None:
    settings = get_settings()

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=False,
        log_config=None,
        server_header=False,
        date_header=False,
        timeout_graceful_shutdown=8,
    )


if __name__ == "__main__":
    main()
