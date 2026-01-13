# Human Review UI

**Spec ID**: 09  
**Status**: Final  
**Dependencies**: React, FastAPI, Cloud Run, IAP

---

## 1. Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend | React (Vite) + Tailwind + shadcn/ui | Modern DX, AI-friendly codegen |
| Backend | FastAPI (Python 3.11) | Shares Pydantic with pipeline |
| Hosting | Cloud Run | Serverless, scales to zero |
| Auth | IAP + Google Workspace SSO | Zero custom auth |
| State | Firestore (via pipeline) | Real-time sync |

---

## 2. Features (MVP)

### 2.1 Dashboard

- Today's processing count
- Success rate (7-day rolling)
- Pending review count
- Pro budget usage
- Recent activity feed

### 2.2 FAILED Document List

- Quarantined files with error reasons
- Filter by date, document type, error type
- Sort by date, urgency
- Bulk selection for batch operations

### 2.3 Document Review

- Side-by-side: PDF (left) + Form (right)
- Inline JSON editor with validation
- Field-level error highlighting
- Migration warning display
- Quality warnings display

### 2.4 Actions

- **Approve**: Validate → Trigger Saga resume
- **Reject**: Mark as permanently rejected
- **Export**: Download corrected JSON

---

## 3. UI Wireframes

### 3.1 Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  OCR Pipeline                                    [User Menu ▼]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Today       │  │  Success     │  │  Pending     │          │
│  │     47       │  │    94.2%     │  │      3       │          │
│  │  processed   │  │  (7 days)    │  │   review     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Recent Activity                                          │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  10:30  ✓ INV-2025-001 processed successfully            │  │
│  │  10:28  ✗ DL-00123 failed (management_id invalid)        │  │
│  │  10:25  ✓ INV-2025-002 processed successfully            │  │
│  │  10:20  ⚠ INV-2025-003 approved by user@example.com      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [View All Failed Documents →]                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 FAILED Documents List

```
┌─────────────────────────────────────────────────────────────────┐
│  Failed Documents                           [Filter ▼] [Sort ▼] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ☐ ⚠️  invoice_scan_001.pdf                   2025-01-09 │   │
│  │      Error: management_id format invalid                 │   │
│  │      Attempts: 3 (Flash ×2, Pro ×1)                     │   │
│  │      Type: delivery_note                    [Review →]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ☐ ⚠️  delivery_note_feb.pdf                  2025-01-08 │   │
│  │      Error: company_name not in vendor master           │   │
│  │      Attempts: 2 (Flash ×2)                             │   │
│  │      Type: delivery_note                    [Review →]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ☐ ⚠️  receipt_thermal_003.pdf               2025-01-08 │   │
│  │      Error: issue_date could not be parsed              │   │
│  │      Attempts: 3 (Flash ×2, Pro ×1)                     │   │
│  │      Type: invoice                          [Review →]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [← Prev]  Page 1 of 3  [Next →]                                │
│                                                                  │
│  Selected: 0  [Bulk Reject]                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Document Review (Side-by-Side)

```
┌─────────────────────────────────────────────────────────────────┐
│  Review: invoice_scan_001.pdf                        [← Back]   │
├────────────────────────────┬────────────────────────────────────┤
│                            │                                    │
│                            │  ┌────────────────────────────┐   │
│                            │  │ ⚠️ Migrated Data           │   │
│                            │  │ Fields need verification:  │   │
│                            │  │ • total_amount             │   │
│   ┌──────────────────┐     │  └────────────────────────────┘   │
│   │                  │     │                                    │
│   │                  │     │  Management ID *                   │
│   │   PDF Preview    │     │  ┌────────────────────────────┐   │
│   │                  │     │  │ INV-X                      │   │
│   │   (Zoomable,     │     │  └────────────────────────────┘   │
│   │    Scrollable)   │     │  ❌ Invalid format (6-20 chars)   │
│   │                  │     │                                    │
│   │                  │     │  Company Name *                    │
│   │                  │     │  ┌────────────────────────────┐   │
│   │                  │     │  │ 山田商事                   │   │
│   │                  │     │  └────────────────────────────┘   │
│   │                  │     │  ✓ Valid                          │
│   │                  │     │                                    │
│   └──────────────────┘     │  Issue Date *                      │
│                            │  ┌────────────────────────────┐   │
│   [Zoom +] [Zoom -]        │  │ 2025-01-13                 │   │
│   [Rotate] [Full Screen]   │  └────────────────────────────┘   │
│                            │  ✓ Valid                          │
│                            │                                    │
│                            │  Total Amount *                    │
│                            │  ┌────────────────────────────┐   │
│                            │  │ 0                     ⚠️   │   │
│                            │  └────────────────────────────┘   │
│                            │  ⚠️ Needs verification (migrated) │
│                            │                                    │
│                            │  ┌────────────┐ ┌────────────┐    │
│                            │  │  Approve   │ │   Reject   │    │
│                            │  └────────────┘ └────────────┘    │
│                            │                                    │
└────────────────────────────┴────────────────────────────────────┘
```

---

## 4. API Endpoints

### 4.1 Dashboard

```python
@app.get("/api/dashboard")
async def get_dashboard(request: Request) -> DashboardResponse:
    """Get dashboard summary data."""
    user = get_iap_user(request)
    
    return DashboardResponse(
        today_count=await count_documents_today(),
        success_rate_7d=await calculate_success_rate(days=7),
        pending_review=await count_pending_documents(),
        pro_usage=await get_pro_usage(),
        recent_activity=await get_recent_activity(limit=10)
    )
```

### 4.2 Document List

```python
@app.get("/api/documents/failed")
async def list_failed_documents(
    page: int = 1,
    limit: int = 20,
    document_type: Optional[str] = None,
    error_type: Optional[str] = None,
    sort: str = "created_at:desc"
) -> PaginatedResponse[FailedDocument]:
    """List documents requiring review."""
    
    query = build_query(
        status="FAILED",
        document_type=document_type,
        error_type=error_type
    )
    
    documents = await query_documents(query, page, limit, sort)
    total = await count_documents(query)
    
    return PaginatedResponse(
        items=documents,
        total=total,
        page=page,
        pages=ceil(total / limit)
    )
```

### 4.3 Document Detail

```python
@app.get("/api/documents/{doc_hash}")
async def get_document(doc_hash: str) -> DocumentDetail:
    """Get full document detail for review."""
    
    doc = await fetch_document(doc_hash)
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Get PDF URL (signed, temporary)
    pdf_url = generate_signed_url(doc.quarantine_path, expiry=3600)
    
    # Get extraction attempts
    attempts = await fetch_extraction_attempts(doc_hash)
    
    return DocumentDetail(
        hash=doc_hash,
        status=doc.status,
        document_type=doc.document_type,
        extracted_data=doc.extracted_data,
        validation_errors=doc.validation_errors,
        quality_warnings=doc.quality_warnings,
        migration_metadata=doc.migration_metadata,
        attempts=attempts,
        pdf_url=pdf_url,
        created_at=doc.created_at
    )
```

### 4.4 Update Document

```python
@app.put("/api/documents/{doc_hash}")
async def update_document(
    doc_hash: str,
    data: DocumentUpdate,
    request: Request
) -> UpdateResponse:
    """Save corrected data (does not approve)."""
    
    user = get_iap_user(request)
    
    # Validate against schema
    schema_class = get_schema(data.document_type)
    try:
        validated = schema_class(**data.corrected_data)
    except ValidationError as e:
        raise HTTPException(400, {"validation_errors": e.errors()})
    
    # Save draft
    await save_document_draft(doc_hash, data.corrected_data, user["email"])
    
    # Audit log
    audit_log(
        action="DATA_CORRECTED",
        resource=doc_hash,
        actor=user["email"],
        details={"changes": data.changes}
    )
    
    return UpdateResponse(status="saved")
```

### 4.5 Approve Document

```python
@app.post("/api/documents/{doc_hash}/approve")
async def approve_document(
    doc_hash: str,
    request: Request
) -> ApproveResponse:
    """Approve and resubmit document."""
    
    user = get_iap_user(request)
    
    # Fetch current data
    doc = await fetch_document(doc_hash)
    if doc.status != "FAILED":
        raise HTTPException(400, f"Cannot approve document with status: {doc.status}")
    
    # Validate with Gate Linter
    gate_result = GateLinter.validate(doc.corrected_data or doc.extracted_data)
    if not gate_result.passed:
        raise HTTPException(400, {
            "message": "Gate validation failed",
            "errors": gate_result.errors
        })
    
    # Trigger Saga resume
    await trigger_saga_resume(doc_hash)
    
    # Audit log
    audit_log(
        action="DOCUMENT_APPROVED",
        resource=doc_hash,
        actor=user["email"],
        details={
            "quality_warnings_count": len(doc.quality_warnings or [])
        }
    )
    
    return ApproveResponse(
        status="approved",
        message="Document queued for processing"
    )
```

### 4.6 Reject Document

```python
@app.post("/api/documents/{doc_hash}/reject")
async def reject_document(
    doc_hash: str,
    body: RejectRequest,
    request: Request
) -> RejectResponse:
    """Permanently reject document."""
    
    user = get_iap_user(request)
    
    await update_document_status(
        doc_hash,
        status="REJECTED",
        rejection_reason=body.reason,
        rejected_by=user["email"]
    )
    
    audit_log(
        action="DOCUMENT_REJECTED",
        resource=doc_hash,
        actor=user["email"],
        details={"reason": body.reason}
    )
    
    return RejectResponse(status="rejected")
```

---

## 5. React Components

### 5.1 PDF Viewer

```tsx
// components/PDFViewer.tsx
import { useState } from "react";
import { Document, Page } from "react-pdf";
import { ZoomIn, ZoomOut, RotateCw, Maximize } from "lucide-react";

interface Props {
  url: string;
}

export function PDFViewer({ url }: Props) {
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [rotation, setRotation] = useState(0);
  
  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex gap-2 p-2 border-b">
        <button onClick={() => setScale(s => Math.min(s + 0.25, 3))}>
          <ZoomIn className="h-4 w-4" />
        </button>
        <button onClick={() => setScale(s => Math.max(s - 0.25, 0.5))}>
          <ZoomOut className="h-4 w-4" />
        </button>
        <button onClick={() => setRotation(r => (r + 90) % 360)}>
          <RotateCw className="h-4 w-4" />
        </button>
        <span className="text-sm text-gray-500">{Math.round(scale * 100)}%</span>
      </div>
      
      {/* PDF */}
      <div className="flex-1 overflow-auto p-4 bg-gray-100">
        <Document
          file={url}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        >
          {Array.from({ length: numPages }, (_, i) => (
            <Page
              key={i}
              pageNumber={i + 1}
              scale={scale}
              rotate={rotation}
              className="mb-4 shadow-lg"
            />
          ))}
        </Document>
      </div>
    </div>
  );
}
```

### 5.2 Editable Field

```tsx
// components/EditableField.tsx
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

interface Props {
  name: string;
  label: string;
  value: any;
  error?: string;
  isDefaulted?: boolean;
  onChange: (value: any) => void;
}

export function EditableField({
  name,
  label,
  value,
  error,
  isDefaulted,
  onChange
}: Props) {
  const hasError = !!error;
  
  return (
    <div className={`p-3 rounded-lg ${
      hasError ? "bg-red-50 border-2 border-red-300" :
      isDefaulted ? "bg-amber-50 border-2 border-amber-300" :
      "bg-gray-50 border border-gray-200"
    }`}>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {isDefaulted && (
          <span className="ml-2 text-xs text-amber-600">
            <AlertTriangle className="inline h-3 w-3" /> Needs verification
          </span>
        )}
      </label>
      
      <input
        type="text"
        name={name}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full p-2 border rounded focus:ring-2 ${
          hasError ? "border-red-400 focus:ring-red-500" :
          isDefaulted ? "border-amber-400 focus:ring-amber-500" :
          "border-gray-300 focus:ring-blue-500"
        }`}
      />
      
      <div className="mt-1 flex items-center gap-1 text-sm">
        {hasError ? (
          <>
            <XCircle className="h-4 w-4 text-red-500" />
            <span className="text-red-600">{error}</span>
          </>
        ) : (
          <>
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-green-600">Valid</span>
          </>
        )}
      </div>
    </div>
  );
}
```

### 5.3 Review Form

```tsx
// components/ReviewForm.tsx
import { useState } from "react";
import { EditableField } from "./EditableField";
import { MigrationWarning } from "./MigrationWarning";
import { QualityWarnings } from "./QualityWarnings";

interface Props {
  document: DocumentDetail;
  onSave: (data: any) => Promise<void>;
  onApprove: () => Promise<void>;
  onReject: (reason: string) => Promise<void>;
}

export function ReviewForm({ document, onSave, onApprove, onReject }: Props) {
  const [formData, setFormData] = useState(document.extracted_data);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  
  const migrationMetadata = document.migration_metadata;
  const defaultedFields = new Set(migrationMetadata?.fields_defaulted || []);
  
  const handleChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };
  
  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(formData);
    } finally {
      setSaving(false);
    }
  };
  
  return (
    <div className="space-y-4">
      {/* Migration Warning */}
      <MigrationWarning metadata={migrationMetadata} />
      
      {/* Quality Warnings */}
      <QualityWarnings warnings={document.quality_warnings} />
      
      {/* Form Fields */}
      <EditableField
        name="management_id"
        label="Management ID"
        value={formData.management_id}
        error={errors.management_id}
        onChange={(v) => handleChange("management_id", v)}
      />
      
      <EditableField
        name="company_name"
        label="Company Name"
        value={formData.company_name}
        error={errors.company_name}
        onChange={(v) => handleChange("company_name", v)}
      />
      
      <EditableField
        name="issue_date"
        label="Issue Date"
        value={formData.issue_date}
        error={errors.issue_date}
        onChange={(v) => handleChange("issue_date", v)}
      />
      
      <EditableField
        name="total_amount"
        label="Total Amount"
        value={formData.total_amount}
        error={errors.total_amount}
        isDefaulted={defaultedFields.has("total_amount")}
        onChange={(v) => handleChange("total_amount", parseInt(v) || 0)}
      />
      
      {/* Actions */}
      <div className="flex gap-3 pt-4 border-t">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300"
        >
          {saving ? "Saving..." : "Save Draft"}
        </button>
        
        <button
          onClick={onApprove}
          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
        >
          Approve
        </button>
        
        <button
          onClick={() => {
            const reason = prompt("Rejection reason:");
            if (reason) onReject(reason);
          }}
          className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
```

---

## 6. Deployment

### 6.1 Dockerfile

```dockerfile
# Dockerfile
FROM node:20-slim AS frontend-build
WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

# Install dependencies
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy API code
COPY api/ ./api/

# Copy frontend build
COPY --from=frontend-build /app/ui/dist ./static/

# Run FastAPI
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 6.2 Cloud Run Service

```yaml
# service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: ocr-review-ui
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "0"
        autoscaling.knative.dev/maxScale: "3"
    spec:
      serviceAccountName: sa-review-ui
      containers:
        - image: gcr.io/PROJECT/review-ui:latest
          ports:
            - containerPort: 8080
          resources:
            limits:
              memory: 512Mi
              cpu: "1"
          env:
            - name: PROJECT_ID
              value: "PROJECT"
            - name: FIRESTORE_DATABASE
              value: "(default)"
```
