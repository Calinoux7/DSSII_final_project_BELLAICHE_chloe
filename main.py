from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from database import engine, Base
import auth, todos, integrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Todo Management API",
    description="DSS2 Project - RESTful Todo API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = {}
    for e in exc.errors():
        # Extract field name from loc tuple
        loc = e.get("loc", [])
        field = str(loc[-1]) if loc else "general"
        errors.setdefault(field, []).append(e["msg"])
    return JSONResponse(
        status_code=400,
        content={
            "type": "https://httpstatuses.com/400",
            "title": "Validation failed",
            "status": 400,
            "errors": errors,
        },
    )


app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(todos.router, prefix="/api/todos", tags=["Todos"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["Integrations"])


@app.get("/")
def root():
    return {"message": "Todo API is running on port 3087"}
