"""
FastAPI app entrypoint for the Employee 201 File PDF service.

Run locally with (from the project root, C:\\Users\\rtjer\\employee201):
    uvicorn app.main:app --reload
"""
import logging

from dotenv import load_dotenv

# Must run before any app.* import below - aggregator.py reads BASE_URL
# from os.environ at module import time (a bare module-level assignment,
# not read inside a function), so the .env file has to be loaded into the
# environment before that import line executes, or os.environ["BASE_URL"]
# will be empty regardless of whether .env itself is correct.
load_dotenv()

from fastapi import FastAPI

from app.routers.employee201 import router as employee201_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Employee 201 File Generator")

app.include_router(employee201_router)