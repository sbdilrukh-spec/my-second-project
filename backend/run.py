import os

import uvicorn

if __name__ == "__main__":
    # На Render/Railway/Heroku порт приходит через ENV PORT.
    # В локальном dev-режиме PORT не задан — используем 8000.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
