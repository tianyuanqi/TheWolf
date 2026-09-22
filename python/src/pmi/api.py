from __future__ import annotations

from fastapi import FastAPI, HTTPException

from pmi.storage import demo_research, document_evidence, initialize_demo_data


app = FastAPI(title="TheWolf Local Service", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    initialize_demo_data()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "thewolf-local-service", "storage": "sqlite"}


@app.get("/api/demo/research")
def research_demo() -> dict:
    return demo_research()


@app.get("/api/documents/{document_id}/evidence")
def evidence(document_id: str) -> dict:
    item = document_evidence(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="document was not found")
    return item
