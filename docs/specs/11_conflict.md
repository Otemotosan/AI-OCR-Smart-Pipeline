# Concurrent Edit Control

**Spec ID**: 11  
**Status**: Final  
**Dependencies**: Firestore

---

## 1. Problem Statement

Multiple users editing the same document simultaneously:
- User A opens document, starts editing
- User B opens same document, makes changes, saves
- User A saves → overwrites User B's changes

**Result**: Data loss, inconsistent state.

---

## 2. Design

### 2.1 Optimistic Locking

Use `updated_at` timestamp as version marker:
1. Client fetches document with `updated_at`
2. Client sends `expected_updated_at` with save request
3. Server checks if `expected_updated_at` matches current
4. If mismatch → reject with CONFLICT error

### 2.2 Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 OPTIMISTIC LOCKING FLOW                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  User A                          User B                      │
│    │                               │                         │
│    │ GET /doc/123                  │                         │
│    │ updated_at: T1                │                         │
│    │◀──────────────────────────────│                         │
│    │                               │                         │
│    │                               │ GET /doc/123            │
│    │                               │ updated_at: T1          │
│    │                               │◀────────────────────    │
│    │                               │                         │
│    │                               │ PUT /doc/123            │
│    │                               │ expected: T1            │
│    │                               │────────────────────▶    │
│    │                               │                         │
│    │                               │ 200 OK                  │
│    │                               │ updated_at: T2          │
│    │                               │◀────────────────────    │
│    │                               │                         │
│    │ PUT /doc/123                  │                         │
│    │ expected: T1  ← stale!        │                         │
│    │────────────────────────────▶  │                         │
│    │                               │                         │
│    │ 409 CONFLICT                  │                         │
│    │ "Modified by another user"    │                         │
│    │◀──────────────────────────────│                         │
│    │                               │                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Implementation

### 3.1 Backend

```python
# api/routes/documents.py
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime
from google.cloud import firestore

router = APIRouter(prefix="/api/documents")

class ConflictError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


@router.put("/{doc_hash}")
async def update_document(
    doc_hash: str,
    body: UpdateRequest,
    request: Request
):
    """
    Update document with optimistic locking.
    
    Body must include:
    - corrected_data: dict
    - expected_updated_at: str (ISO format)
    """
    user = get_iap_user(request)
    db = firestore.Client()
    doc_ref = db.collection("processed_documents").document(doc_hash)
    
    @firestore.transactional
    def _update(transaction):
        doc = doc_ref.get(transaction=transaction)
        
        if not doc.exists:
            raise HTTPException(404, "Document not found")
        
        current_data = doc.to_dict()
        current_updated_at = current_data.get("updated_at")
        
        # Convert to comparable format
        if hasattr(current_updated_at, 'isoformat'):
            current_updated_at = current_updated_at.isoformat()
        
        # Conflict detection
        if str(current_updated_at) != body.expected_updated_at:
            raise ConflictError(
                f"Document was modified by {current_data.get('last_modified_by', 'another user')}. "
                f"Please reload the page and try again."
            )
        
        # Perform update
        transaction.update(doc_ref, {
            "corrected_data": body.corrected_data,
            "last_modified_by": user["email"],
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
    
    _update(db.transaction())
    
    # Fetch updated document
    updated_doc = doc_ref.get().to_dict()
    
    return {
        "status": "saved",
        "updated_at": updated_doc["updated_at"].isoformat()
    }
```

### 3.2 Frontend Hook

```typescript
// ui/hooks/useOptimisticSave.ts
import { useState, useCallback } from "react";

interface SaveState {
  saving: boolean;
  error: string | null;
  conflict: boolean;
}

interface SaveResult {
  status: "saved" | "conflict" | "error";
  updated_at?: string;
  message?: string;
}

export function useOptimisticSave(docHash: string) {
  const [state, setState] = useState<SaveState>({
    saving: false,
    error: null,
    conflict: false,
  });
  
  const save = useCallback(async (
    data: Record<string, any>,
    expectedUpdatedAt: string
  ): Promise<SaveResult> => {
    setState({ saving: true, error: null, conflict: false });
    
    try {
      const res = await fetch(`/api/documents/${docHash}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corrected_data: data,
          expected_updated_at: expectedUpdatedAt,
        }),
      });
      
      if (res.status === 409) {
        const detail = await res.json();
        setState({ saving: false, error: detail.detail, conflict: true });
        return { status: "conflict", message: detail.detail };
      }
      
      if (!res.ok) {
        const detail = await res.json();
        setState({ saving: false, error: detail.detail || "Save failed", conflict: false });
        return { status: "error", message: detail.detail };
      }
      
      const result = await res.json();
      setState({ saving: false, error: null, conflict: false });
      return { status: "saved", updated_at: result.updated_at };
      
    } catch (e) {
      const message = e instanceof Error ? e.message : "Network error";
      setState({ saving: false, error: message, conflict: false });
      return { status: "error", message };
    }
  }, [docHash]);
  
  return { ...state, save };
}
```

### 3.3 Conflict Dialog Component

```tsx
// ui/components/ConflictDialog.tsx
import { AlertTriangle, RefreshCw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  open: boolean;
  message: string;
  onReload: () => void;
  onClose: () => void;
}

export function ConflictDialog({ open, message, onReload, onClose }: Props) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-amber-600">
            <AlertTriangle className="h-5 w-5" />
            Edit Conflict
          </DialogTitle>
          <DialogDescription>
            {message}
          </DialogDescription>
        </DialogHeader>
        
        <div className="py-4 text-sm text-gray-600">
          <p>Your changes could not be saved because someone else modified this document.</p>
          <p className="mt-2">Options:</p>
          <ul className="list-disc list-inside mt-1">
            <li><strong>Reload</strong>: Load the latest version (your changes will be lost)</li>
            <li><strong>Copy</strong>: Copy your changes to clipboard, then reload</li>
          </ul>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="default" onClick={onReload}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Reload Page
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### 3.4 Usage in Review Form

```tsx
// ui/components/ReviewForm.tsx
import { useState } from "react";
import { useOptimisticSave } from "../hooks/useOptimisticSave";
import { ConflictDialog } from "./ConflictDialog";

export function ReviewForm({ document }: { document: DocumentDetail }) {
  const [formData, setFormData] = useState(document.corrected_data || document.extracted_data);
  const [updatedAt, setUpdatedAt] = useState(document.updated_at);
  const [showConflict, setShowConflict] = useState(false);
  const [conflictMessage, setConflictMessage] = useState("");
  
  const { saving, error, conflict, save } = useOptimisticSave(document.hash);
  
  const handleSave = async () => {
    const result = await save(formData, updatedAt);
    
    if (result.status === "saved") {
      setUpdatedAt(result.updated_at!);
      toast.success("Saved successfully");
    } else if (result.status === "conflict") {
      setConflictMessage(result.message!);
      setShowConflict(true);
    } else {
      toast.error(result.message || "Save failed");
    }
  };
  
  const handleReload = () => {
    window.location.reload();
  };
  
  return (
    <>
      {/* Form fields... */}
      
      <Button onClick={handleSave} disabled={saving}>
        {saving ? "Saving..." : "Save"}
      </Button>
      
      <ConflictDialog
        open={showConflict}
        message={conflictMessage}
        onReload={handleReload}
        onClose={() => setShowConflict(false)}
      />
    </>
  );
}
```

---

## 4. Audit Trail Integration

Log both successful saves and conflicts:

```python
def log_save_attempt(
    doc_hash: str,
    user: str,
    success: bool,
    conflict: bool = False,
    conflicting_user: str | None = None
):
    """Log save attempt for audit."""
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "doc_hash": doc_hash,
        "action": "SAVE_ATTEMPT",
        "user": user,
        "success": success,
        "conflict": conflict,
        "conflicting_user": conflicting_user,
    }
    
    db.collection("audit_logs").add(audit_entry)
```

---

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Same user, multiple tabs | Each tab tracks own `updated_at`, conflict possible |
| User saves, immediately saves again | Second save uses new `updated_at`, succeeds |
| Document approved while editing | Approval changes `updated_at`, edit blocked |
| Network timeout during save | Client retries with same `expected_updated_at` |
| Server clock skew | Use Firestore `SERVER_TIMESTAMP` for consistency |

---

## 6. Alternative: Pessimistic Locking

Not recommended for this system because:
- Low concurrency (100 docs/month, 1-2 users)
- Lock management complexity
- Risk of zombie locks

Optimistic locking is simpler and sufficient for expected load.
