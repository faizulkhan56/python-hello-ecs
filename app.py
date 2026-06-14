from fastapi import FastAPI
from datetime import datetime

app = FastAPI()


@app.get("/")
def home():
    return {
        "message": "Hello from Python app running on AWS ECS!",
        "version": "v1",
        "time": datetime.utcnow().isoformat()
    }


@app.get("/health")
def health():
    return {"status": "ok"}