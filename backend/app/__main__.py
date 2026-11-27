"""Run the API with ``python -m app`` (development convenience)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.asgi:app", host="0.0.0.0", port=8000, reload=False)
