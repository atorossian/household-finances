from fastapi import FastAPI
from app.api import entries, users

app = FastAPI()

app.include_router(entries.router, prefix="/entries", tags=["Entries"])
app.include_router(users.router, prefix="/users", tags=["Users"])