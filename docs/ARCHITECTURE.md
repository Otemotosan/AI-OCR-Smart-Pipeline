# AI-OCR Smart Pipeline - Architecture Overview

**Version**: 2.1  
**Status**: Production-Ready  
**Last Updated**: 2025-01-09

---

## 1. Executive Summary

A serverless, AI-native pipeline that automates classification, renaming, and filing of non-standard business documents. Extracts **Management ID**, **Company Name**, and **Date** from invoices/delivery notes, organizes files into structured folders, and builds a queryable JSON database.

### Core Metrics

| Metric | Target |
|--------|--------|
| Automation Rate | >95% for Gate criteria |
| Self-Correction Rate | >80% of failures resolved via AI feedback |
| Failure Transparency | 100% traceability |
| Monthly Volume | ~100 documents |

---

## 2. System Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   INPUT      │────▶│  PERCEPTION  │────▶│  COGNITION   │
│              │     │              │     │              │
│ Google Drive │     │ Document AI  │     │ Gemini Flash │
│ Webhook      │     │ Layout Parse │     │ / Pro        │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   OUTPUT     │◀────│  PERSIST     │◀────│  VALIDATE    │
│              │     │              │     │              │
│ Review UI    │     │ Saga Pattern │     │ Gate/Quality │
│ BigQuery     │     │ GCS + DB     │     │ Linters      │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## 3. Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Trigger | Cloud Functions 2nd Gen | Event-driven, serverless |
| OCR | Document AI (Layout Parser) | Structure + coordinates |
| Reasoning | Gemini 2.0 Flash / 1.5 Pro | Cost-efficient + deep fallback |
| Validation | Pydantic + Custom Linters | Schema enforcement |
| Retry | Tenacity | Configurable backoff |
| Persistence | BigQuery + Cloud SQL + GCS | Analytics + master data + files |
| Idempotency | Firestore | Atomic locks, serverless |
| Review UI | React + FastAPI + Cloud Run | Modern stack, shares Pydantic |
| Auth | IAP + Google Workspace SSO | Zero custom auth code |
| Encryption | CMEK (Cloud KMS) | Customer-managed keys |

---

## 4. Key Design Decisions

### 4.1 Two-Tier Linter Architecture

| Linter | Purpose | On Failure |
|--------|---------|------------|
| **Gate** (Invariants) | Naming, filing, classification | Block persistence |
| **Quality** (Variables) | Business rules, data quality | Warning only |

→ Details: [`specs/06_linters.md`](specs/06_linters.md)

### 4.2 Conditional Image Attachment

| Condition | Input to Gemini |
|-----------|-----------------|
| Default | Markdown only |
| Confidence < 0.85 | Markdown + Image |
| Gate Linter failed | Markdown + Image |
| Fragile doc type | Markdown + Image |

→ Details: [`specs/04_confidence.md`](specs/04_confidence.md)

### 4.3 Smart Escalation

```
Flash (syntax error) → Flash retry x2
Flash (semantic error) → Pro escalation (budget: 50/day)
Pro failure → Human review
```

→ Details: [`specs/02_retry.md`](specs/02_retry.md)

### 4.4 Saga Pattern for Atomicity

```
DB(PENDING) → GCS(copy) → GCS(delete source) → DB(COMPLETED)
     ↑                                              │
     └──────── Compensation on failure ◀────────────┘
```

→ Details: [`specs/03_saga.md`](specs/03_saga.md)

---

## 5. Specification Index

| File | Contents |
|------|----------|
| [`specs/01_idempotency.md`](specs/01_idempotency.md) | SHA-256 hashing, Firestore locks, heartbeat |
| [`specs/02_retry.md`](specs/02_retry.md) | Error classification, Tenacity config, Pro budget |
| [`specs/03_saga.md`](specs/03_saga.md) | Compensation transactions, rollback flow |
| [`specs/04_confidence.md`](specs/04_confidence.md) | Doc AI confidence, image attachment logic, prompt priority |
| [`specs/05_schema.md`](specs/05_schema.md) | Registry design, versioning, migration metadata |
| [`specs/06_linters.md`](specs/06_linters.md) | Gate/Quality separation, YAML config |
| [`specs/07_monitoring.md`](specs/07_monitoring.md) | Metrics, alerts, structured logging |
| [`specs/08_security.md`](specs/08_security.md) | Service accounts, CMEK, IAP, audit logs |
| [`specs/09_review_ui.md`](specs/09_review_ui.md) | React/FastAPI stack, features, API endpoints |

---

## 6. Folder Structure (Implementation)

```
src/
├── core/
│   ├── schemas.py          # Pydantic models + SCHEMA_REGISTRY
│   ├── linters/
│   │   ├── gate.py         # Invariant validation
│   │   └── quality.py      # Configurable validation
│   ├── prompts.py          # Gemini system prompts
│   ├── lock.py             # Firestore distributed lock
│   └── saga.py             # Saga orchestrator
├── functions/
│   └── processor/          # Cloud Function entry point
├── api/
│   └── main.py             # FastAPI for Review UI
└── ui/
    └── src/                # React application
config/
├── quality_rules.yaml
└── alerts.yaml
```

---

## 7. Development Roadmap

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1. Foundation | Week 1-2 | Schema registry, Gate Linter, Firestore lock |
| 2. Core Pipeline | Week 3-4 | Doc AI, Gemini, self-correction loop |
| 3. Escalation | Week 5-6 | Pro logic, BigQuery, FAILED reports |
| 4. Review UI | Week 7-8 | Dashboard, editor, approve flow |
| 5. Hardening | Week 9-10 | Monitoring, security audit, load test |

---

## 8. Quick Reference

### Entry Points

- **Pipeline Trigger**: `gs://bucket/input/*` → Cloud Function
- **Review UI**: `https://review.example.com` (IAP-protected)
- **Metrics**: Cloud Monitoring dashboard

### Key Thresholds

| Parameter | Value |
|-----------|-------|
| Confidence threshold | 0.85 |
| Flash retry limit | 2 |
| Pro daily budget | 50 calls |
| Pro monthly budget | 1,000 calls |
| Lock TTL | 600s (with heartbeat) |
| Heartbeat interval | 120s |

### Alert Escalation

| Severity | Condition | Channel |
|----------|-----------|---------|
| P0 | Queue backlog >100 | Slack + PagerDuty |
| P1 | Failure rate >5%/hr | Slack + PagerDuty |
| P2 | Pro budget >80% | Slack |

---

## Appendix: Glossary

| Term | Definition |
|------|------------|
| Gate Linter | Immutable rules blocking persistence on failure |
| Quality Linter | Configurable rules producing warnings |
| Saga Pattern | Distributed transaction with compensating actions |
| SSOT | Single Source of Truth |
| CMEK | Customer-Managed Encryption Keys |
| IAP | Identity-Aware Proxy |
