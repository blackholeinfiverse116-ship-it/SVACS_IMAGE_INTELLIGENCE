#!/usr/bin/env python3
"""
svacs_service.py

SVACS Maritime Intelligence Runtime — HTTP Service.

Thin FastAPI shell exposing intelligence.vessel_intelligence_engine over
HTTP. Contains no reasoning, confidence, explainability, risk, or
validation logic of its own — it only routes HTTP requests into
vessel_intelligence_engine.process_intelligence() and
svacs.runtime.SVACSRuntime.replay().
"""
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from intelligence.vessel_intelligence_engine import process_intelligence, _get_runtime

PORT = 8006

app = FastAPI(
    title="SVACS Maritime Intelligence Runtime",
    description=(
        "Consumes Samachar / AIS / manual structured intelligence and "
        "produces evidence-backed maritime intelligence with risk and "
        "validation gating."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    intel: Dict[str, Any]
    observation_source: Optional[str] = None


class ProcessResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


@app.post("/api/svacs/process", response_model=ProcessResponse)
async def svacs_process(req: ProcessRequest):
    try:
        result = process_intelligence(req.intel, observation_source=req.observation_source)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ProcessResponse(success=True, data=result)


@app.get("/api/svacs/replay/{trace_id}")
async def svacs_replay(trace_id: str):
    runtime = _get_runtime()
    try:
        replay = runtime.replay(trace_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"success": True, "data": replay}


@app.get("/api/svacs/health")
async def health():
    runtime = _get_runtime()
    trace_count = len(runtime.bucket_store.list_trace_ids())
    return {
        "status": "healthy",
        "bucket": {
            "path": runtime.bucket_store.directory,
            "records_stored": trace_count,
        },
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)