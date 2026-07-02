"""
FastAPI app entrypoint for the Employee 201 File PDF service.

Run locally with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.routers.employee201 import router as employee201_router

app = FastAPI(title="Employee 201 File Generator")

app.include_router(employee201_router)