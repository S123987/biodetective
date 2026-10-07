"""Start BioDetective as a private, browser-based web application."""

from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    if os.getenv("BIODETECTIVE_OPEN_BROWSER", "1") != "0":
        url = "http://127.0.0.1:" + str(port)

        def open_app() -> None:
            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=open_app, daemon=True).start()
    uvicorn.run("biodetective.webapp:app", host="127.0.0.1", port=port, reload=False)

