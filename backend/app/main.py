from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import dashboard, encounters, flags, patients, suggestions

app = FastAPI(
    title="Clinical Encounter Intelligence System",
    description="Structured extraction, anomaly flags and AI audit logging for clinical encounter notes.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (dashboard, patients, encounters, flags, suggestions):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}
