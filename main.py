from fastapi import FastAPI
from app.api.routes import auth, cases, observations, twin, eval as eval_routes

app = FastAPI(title="NyayaOS", version="0.1.0")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(observations.router, prefix="/observations", tags=["observations"])
app.include_router(twin.router, prefix="/twin", tags=["twin"])
app.include_router(eval_routes.router, prefix="/eval", tags=["eval"])

@app.get("/health")
def health():
    return {"status": "ok"}
