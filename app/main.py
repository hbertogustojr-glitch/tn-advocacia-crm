from fastapi import FastAPI

from app.api.crm import crm_router
from app.api.routes import router
from app.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(router)
app.include_router(crm_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
