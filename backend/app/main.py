from fastapi import FastAPI

from .db import connect

app = FastAPI(title="Reinterpret")


@app.get("/api/health")
def health():
    connect().close()  # fails loudly if the database can't be opened
    return {"ok": True}
