"""PyCharm-da bu faylın üstündəki yaşıl ▶ düyməsinə basın — server işə düşür və brauzer
avtomatik açılır. Terminala, `cd`-ə, ya da `activate`-ə ehtiyac yoxdur."""
import threading
import webbrowser

import uvicorn

# 0.0.0.0-a bağlanır ki, Docker-də işləyən n8n `host.docker.internal:8800` ilə bura çata bilsin
# (yalnız 127.0.0.1-ə bağlansaydı, Docker konteynerindən əlçatan olmazdı).
HOST = "0.0.0.0"
PORT = 8800


def _open_browser() -> None:
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Timer(1.5, _open_browser).start()
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
