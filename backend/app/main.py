from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import auth, projects, documents, chats, risks, proposals


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure upload directory exists
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="APIP — Arabic Procurement Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# --- Routers ---
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(chats.router)
app.include_router(risks.router)
app.include_router(proposals.router)



# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "status": 500}},
    )


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed.",
                "details": exc.errors()
            }
        }
    )


# --- Health check ---
@app.get("/health")
async def health():
    return {"status": "ok"}
