from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("PRO_DOWNLOADER_HOST", "0.0.0.0")
    port = int(os.environ.get("PRO_DOWNLOADER_PORT", "8000"))
    uvicorn.run("pro_downloader_server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
