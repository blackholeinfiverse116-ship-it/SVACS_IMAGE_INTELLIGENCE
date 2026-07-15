# SVACS Maritime Intelligence Runtime – Review Packet (Final)

## Project Overview

The SVACS Maritime Intelligence Runtime is designed to process structured maritime intelligence from multiple sources and generate a single evidence-backed intelligence record.

The system accepts intelligence from:

- Image observations (through Samachar)
- AIS (Automatic Identification System)
- Manual operator reports

Instead of maintaining different processing pipelines for each source, every observation passes through one common SVACS pipeline. This ensures deterministic execution, replay safety, explainability, and trace continuity.

The final output includes:

- Vessel Identification
- Maritime Reasoning
- Refined Confidence Score
- Explainability
- Risk Assessment
- Validation Status
- Bucket Storage
- Replay Support

---

# Architecture

```
                    Image Observation
                           │
                           ▼
              Samachar Ingestion Service
                  (Image + OCR Processing)
                           │
                           ▼
               Structured Intelligence
                           │
                           ▼
              Structured Intelligence Consumer
                     (Task 1)
                           │
                           ▼
             Maritime Reasoning Engine
                     (Task 2)
                           │
                           ▼
           Confidence Refinement Engine
                     (Task 3)
                           │
                           ▼
            Explainability Generator
                     (Task 4)
                           │
                           ▼
                 Bucket Store
              (Replay Safe Storage)
                     (Task 5)
                           │
                           ▼
      Vessel Intelligence Engine
 (Risk Assessment + Validation Layer)
                           │
                           ▼
      Dashboard / Replay / NICAI Output
```

All Image, AIS and Manual observations follow this exact pipeline.

There are no duplicate reasoning or confidence engines.

---

# Project Structure

```
SVACS_IMAGE_INTELLIGENCE/

│
├── ingest_service.py
├── requirements.txt
├── REVIEW_PACKET.md
├── test_svacs_runtime.py
├── test_vessel_intelligence_engine.py
├── test_svacs_integration_with_samachar.py
│
├── intelligence/
│      ├── __init__.py
│      └── vessel_intelligence_engine.py
│
├── svacs/
│      ├── consumer.py
│      ├── reasoning_engine.py
│      ├── confidence_engine.py
│      ├── explainability.py
│      ├── bucket_store.py
│      ├── runtime.py
│      ├── service.py
│      ├── knowledge_base.py
│      └── models.py
│
└── data/
```

---

# Main Components

## 1. Samachar Ingestion Service

Responsible for

- Image Upload
- OCR Processing
- Structured Intelligence Generation

Runs on

```
http://127.0.0.1:8005
```

Main File

```
ingest_service.py
```

---

## 2. SVACS Runtime

Responsible for

- Structured Intelligence Processing
- Maritime Reasoning
- Confidence Refinement
- Explainability
- Bucket Storage
- Replay
- Risk Assessment
- Validation Status

Runs on

```
http://127.0.0.1:8006
```

Main File

```
svacs/service.py
```

Run using

```bash
python -m svacs.service
```

---

# Important Files

| File | Purpose |
|------|---------|
| ingest_service.py | Samachar API |
| svacs/service.py | SVACS API |
| svacs/runtime.py | Main Pipeline |
| svacs/consumer.py | Structured Intelligence Consumer |
| svacs/reasoning_engine.py | Maritime Reasoning |
| svacs/confidence_engine.py | Confidence Refinement |
| svacs/explainability.py | Explainability Generation |
| svacs/bucket_store.py | Bucket Storage & Replay |
| svacs/models.py | Canonical Models |
| svacs/knowledge_base.py | Maritime Knowledge Base |
| intelligence/vessel_intelligence_engine.py | Risk Assessment |
| test_svacs_runtime.py | Runtime Tests |
| test_vessel_intelligence_engine.py | Vessel Intelligence Tests |
| test_svacs_integration_with_samachar.py | Integration Test |

---

# How to Run the Project

## Step 1

Open Terminal

Move to the project directory

```bash
cd SVACS_IMAGE_INTELLIGENCE
```

---

## Step 2

Start Samachar Service

```bash
python ingest_service.py
```

Expected Output

```
Uvicorn running on http://0.0.0.0:8005
```

Swagger

```
http://127.0.0.1:8005/docs
```

Health API

```
GET

http://127.0.0.1:8005/api/health
```

Expected Response

```json
{
  "status": "healthy"
}
```

---

## Step 3

Open another terminal

Start SVACS Runtime

```bash
python -m svacs.service
```

Expected Output

```
Uvicorn running on http://0.0.0.0:8006
```

Swagger

```
http://127.0.0.1:8006/docs
```

Health API

```
GET

http://127.0.0.1:8006/api/svacs/health
```

Expected Response

```json
{
    "status":"healthy"
}
```

---

# Running Unit Tests

## Runtime Tests

```bash
python -m unittest test_svacs_runtime.py -v
```

Expected

```
Ran 8 tests

OK
```

---

## Vessel Intelligence Tests

```bash
python -m unittest test_vessel_intelligence_engine.py -v
```

Expected

```
Ran 9 tests

OK
```

---

## Integration Test

```bash
python -m unittest test_svacs_integration_with_samachar.py -v
```

Expected

```
Ran 1 test

OK
```

---

# Available APIs

## Samachar APIs

### Health

```
GET /api/health
```

### Image Ingestion

```
POST /api/ingest/image
```

### List Traces

```
GET /api/ingest/traces
```

### Get Trace

```
GET /api/ingest/trace/{trace_id}
```

---

## SVACS APIs

### Health

```
GET /api/svacs/health
```

### Process Intelligence

```
POST /api/svacs/process
```

### Replay

```
GET /api/svacs/replay/{trace_id}
```

---

# Bucket Store

The Bucket Store automatically stores every processed intelligence record.

It is integrated into the runtime and **does not need to be started separately**.

Responsibilities

- Store processed records
- Maintain Trace IDs
- Replay Intelligence
- Preserve Deterministic Execution
- Dashboard Support
- NICAI Support

Bucket Location

```
svacs/bucket_store/
```

or

```
test_bucket_store/
```

during testing.

---

# Replay Support

Replay allows previously processed intelligence to be reconstructed using its Trace ID.

Example

```
GET

/api/svacs/replay/{trace_id}
```

Replay verifies

- Trace Continuity
- Bucket Record
- Dashboard View
- NICAI View
- Replay Safety

---

# Confidence Refinement

Confidence is calculated using

- Upstream Confidence
- Knowledge Base Verification
- Vessel Dimensions
- AIS Correlation
- Manual Observation Penalty

The Confidence Engine generates a final confidence score together with a complete reasoning trail.

---

# Risk Assessment

The Vessel Intelligence Engine determines

- Risk Level
- Validation Status
- Operator Action Required

Examples

| Risk | Validation |
|-------|------------|
| Low | ALLOW |
| Medium | REVIEW |
| High | DENY |
| Critical | CRITICAL DENY |

---

# Explainability

Every processed intelligence record includes

- Candidate Vessel
- Confidence Breakdown
- Maritime Reasoning
- Runtime Trace
- Knowledge Base Matches
- Evidence Signals

This allows users to understand how the final decision was reached.

---

# What Was Fixed

During development, the major issue occurred in

```
svacs/reasoning_engine.py
```

Problem

Manual and AIS observations were incorrectly marked as `knowledge_verified`, even when there was no actual knowledge-base match. This caused the Confidence Engine to apply an incorrect knowledge bonus.

Solution

The reasoning engine was updated so that

- `knowledge_verified` is now **True only when a real knowledge-base match is found.**
- AIS and Manual observations use their own source-specific confidence adjustments.
- Confidence calculations are now accurate for all observation types.

No changes were required in

- consumer.py
- confidence_engine.py
- runtime.py
- models.py

The fix was isolated to the Reasoning Engine.

---

# Validation Results

All validation steps completed successfully.

✅ Samachar Service Running

✅ SVACS Runtime Running

✅ Runtime Tests Passed (8/8)

✅ Vessel Intelligence Tests Passed (9/9)

✅ Integration Test Passed (1/1)

✅ Health APIs Working

✅ Replay Working

✅ Bucket Storage Working

✅ Trace Continuity Verified

✅ Explainability Generated

✅ Risk Assessment Working

✅ Validation Rules Working

---

# Complete Execution Commands

```bash
# Go to Project

cd SVACS_IMAGE_INTELLIGENCE


# Install Dependencies

pip install -r requirements.txt


# Start Samachar Service

python ingest_service.py


# Open New Terminal


# Start SVACS Runtime

python -m svacs.service


# Runtime Tests

python -m unittest test_svacs_runtime.py -v


# Vessel Intelligence Tests

python -m unittest test_vessel_intelligence_engine.py -v


# Integration Test

python -m unittest test_svacs_integration_with_samachar.py -v
```

---

# Final Output

The project successfully provides a complete maritime intelligence pipeline that:

- Accepts structured intelligence from Image, AIS and Manual observations.
- Uses a single deterministic processing pipeline.
- Performs maritime reasoning using a knowledge base.
- Refines confidence using evidence-based adjustments.
- Generates explainable intelligence.
- Stores replay-safe records.
- Performs operational risk assessment.
- Supports dashboard and NICAI integration.
- Preserves trace continuity across the complete execution lifecycle.

---

# Final Status

| Component | Status |
|-----------|--------|
| Samachar Service | ✅ Running |
| SVACS Runtime | ✅ Running |
| Health APIs | ✅ Working |
| Runtime Tests | ✅ Passed |
| Vessel Intelligence Tests | ✅ Passed |
| Integration Tests | ✅ Passed |
| Bucket Storage | ✅ Working |
| Replay | ✅ Working |
| Explainability | ✅ Working |
| Confidence Refinement | ✅ Working |
| Risk Assessment | ✅ Working |
| Trace Continuity | ✅ Verified |

## Overall Result

**Project Status: SUCCESSFULLY COMPLETED**