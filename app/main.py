from fastapi import FastAPI
from app.api import entries, users, household, accounts, summaries, debts, audit

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(entries.router, prefix="/entries", tags=["Entries"])
app.include_router(debts.router, prefix="/debts", tags=["Debts"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(household.router, prefix="/households", tags=["Households"])
app.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])
app.include_router(summaries.router, prefix="/summaries", tags=["Summaries"])
