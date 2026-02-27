from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AP Invoice Triage API")

@app.get("/health")
def health():
    return {"ok": True}

class Query(BaseModel):
    question: str

@app.post("/triage")
def triage(query: Query):
    return {
        "duplicates": [],
        "high_value": [],
        "reason": "Backend is live. Next step: connect to Supabase tables."
    }