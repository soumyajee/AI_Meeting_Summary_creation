from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as meetings_router
from app.db import create_db_and_tables

app = FastAPI(
    title="AI Meeting Assistant",
    description="AI-powered meeting transcript analysis, Q&A, search, follow-up email, and multi-meeting insights API.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.include_router(meetings_router)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "AI Meeting Assistant API is running.",
        "docs": "/docs",
    }