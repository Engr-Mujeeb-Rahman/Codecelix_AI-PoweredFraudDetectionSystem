from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import assistant, auth, dashboard, fraud, network, risk, rules, transactions

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered Fraud & Risk Detection Platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth & Users"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(risk.router, prefix="/api", tags=["AI Risk Scoring"])
app.include_router(rules.router, prefix="/api/rules", tags=["Rules Engine"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["AI Assistant"])
app.include_router(fraud.router, prefix="/api", tags=["Fraud Domain"])
app.include_router(network.router, prefix="/api/network", tags=["Fraud Network"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.on_event("startup")
def startup():
    import app.models  # noqa: F401 — register all models on the Base metadata
    from app.db.session import Base, engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    try:
        from app.services.rules_engine import seed_default_rules
        with SessionLocal() as db:
            seed_default_rules(db)
    except Exception:
        pass
