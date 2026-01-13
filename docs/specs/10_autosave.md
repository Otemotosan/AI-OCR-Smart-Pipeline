# Auto-save & Draft Recovery

**Spec ID**: 10  
**Status**: Final  
**Dependencies**: Firestore, localStorage

---

## 1. Problem Statement

Session interruptions cause data loss:
- Browser crash
- Network disconnection
- Accidental tab close
- Session timeout

**Result**: User loses correction work → frustration → distrust in system.

---

## 2. Design

### 2.1 Dual-layer Storage

| Layer | Storage | Latency | Reliability |
|-------|---------|---------|-------------|
| L1 | localStorage | Immediate | Browser-local |
| L2 | Firestore `drafts` collection | ~100ms | Cloud-persistent |

### 2.2 Save Strategy

```
User types
    │
    ▼
┌─────────────┐
│ Debounce    │  ← 2 seconds after last keystroke
│ (2000ms)    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ localStorage│  ← Immediate (L1)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Firestore   │  ← Async, fire-and-forget (L2)
│ draft       │
└─────────────┘
```

---

## 3. Implementation

### 3.1 React Hook

```typescript
// ui/hooks/useAutosave.ts
import { useState, useEffect, useCallback, useRef } from "react";
import { debounce } from "lodash";

interface AutosaveState {
  lastSaved: Date | null;
  saving: boolean;
  error: string | null;
}

interface Draft {
  docHash: string;
  data: Record<string, any>;
  savedAt: string;
  userId: string;
}

const AUTOSAVE_INTERVAL = 30_000; // 30 seconds
const DEBOUNCE_DELAY = 2_000;     // 2 seconds after last change

export function useAutosave(
  docHash: string,
  formData: Record<string, any>,
  userId: string
) {
  const [state, setState] = useState<AutosaveState>({
    lastSaved: null,
    saving: false,
    error: null,
  });
  
  const formDataRef = useRef(formData);
  formDataRef.current = formData;
  
  // L1: localStorage (immediate)
  const saveToLocalStorage = useCallback((data: Record<string, any>) => {
    const draft: Draft = {
      docHash,
      data,
      savedAt: new Date().toISOString(),
      userId,
    };
    localStorage.setItem(`draft_${docHash}`, JSON.stringify(draft));
  }, [docHash, userId]);
  
  // L2: Firestore (async)
  const saveToFirestore = useCallback(async (data: Record<string, any>) => {
    setState(s => ({ ...s, saving: true, error: null }));
    
    try {
      await fetch(`/api/documents/${docHash}/draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data, savedAt: new Date().toISOString() }),
      });
      
      setState(s => ({ ...s, lastSaved: new Date(), saving: false }));
    } catch (e) {
      // Silent fail — localStorage backup exists
      console.warn("Firestore draft save failed:", e);
      setState(s => ({ ...s, saving: false, error: "Cloud save failed" }));
    }
  }, [docHash]);
  
  // Debounced save on change
  const debouncedSave = useCallback(
    debounce((data: Record<string, any>) => {
      saveToLocalStorage(data);
      saveToFirestore(data);
    }, DEBOUNCE_DELAY),
    [saveToLocalStorage, saveToFirestore]
  );
  
  // Trigger save on formData change
  useEffect(() => {
    debouncedSave(formData);
    return () => debouncedSave.cancel();
  }, [formData, debouncedSave]);
  
  // Periodic save (belt and suspenders)
  useEffect(() => {
    const interval = setInterval(() => {
      saveToLocalStorage(formDataRef.current);
      saveToFirestore(formDataRef.current);
    }, AUTOSAVE_INTERVAL);
    
    return () => clearInterval(interval);
  }, [saveToLocalStorage, saveToFirestore]);
  
  // Save on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      saveToLocalStorage(formDataRef.current);
      // Note: Firestore save may not complete on unload
    };
    
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [saveToLocalStorage]);
  
  return state;
}
```

### 3.2 Draft Recovery Hook

```typescript
// ui/hooks/useDraftRecovery.ts
import { useState, useEffect } from "react";

interface Draft {
  docHash: string;
  data: Record<string, any>;
  savedAt: string;
  userId: string;
}

interface RecoveryState {
  hasDraft: boolean;
  draft: Draft | null;
  source: "local" | "server" | null;
}

export function useDraftRecovery(
  docHash: string,
  currentData: Record<string, any>
): {
  recovery: RecoveryState;
  applyDraft: () => void;
  discardDraft: () => void;
} {
  const [recovery, setRecovery] = useState<RecoveryState>({
    hasDraft: false,
    draft: null,
    source: null,
  });
  
  useEffect(() => {
    const checkDrafts = async () => {
      // Check localStorage
      const localRaw = localStorage.getItem(`draft_${docHash}`);
      const localDraft: Draft | null = localRaw ? JSON.parse(localRaw) : null;
      
      // Check Firestore
      let serverDraft: Draft | null = null;
      try {
        const res = await fetch(`/api/documents/${docHash}/draft`);
        if (res.ok) {
          serverDraft = await res.json();
        }
      } catch (e) {
        console.warn("Failed to fetch server draft:", e);
      }
      
      // Determine which draft is newer
      let bestDraft: Draft | null = null;
      let source: "local" | "server" | null = null;
      
      if (localDraft && serverDraft) {
        if (new Date(localDraft.savedAt) > new Date(serverDraft.savedAt)) {
          bestDraft = localDraft;
          source = "local";
        } else {
          bestDraft = serverDraft;
          source = "server";
        }
      } else if (localDraft) {
        bestDraft = localDraft;
        source = "local";
      } else if (serverDraft) {
        bestDraft = serverDraft;
        source = "server";
      }
      
      // Check if draft differs from current
      if (bestDraft && JSON.stringify(bestDraft.data) !== JSON.stringify(currentData)) {
        setRecovery({ hasDraft: true, draft: bestDraft, source });
      }
    };
    
    checkDrafts();
  }, [docHash, currentData]);
  
  const applyDraft = () => {
    // Caller should use recovery.draft.data to update form
    setRecovery({ hasDraft: false, draft: null, source: null });
  };
  
  const discardDraft = () => {
    localStorage.removeItem(`draft_${docHash}`);
    fetch(`/api/documents/${docHash}/draft`, { method: "DELETE" });
    setRecovery({ hasDraft: false, draft: null, source: null });
  };
  
  return { recovery, applyDraft, discardDraft };
}
```

### 3.3 Recovery UI Component

```tsx
// ui/components/DraftRecoveryBanner.tsx
import { AlertTriangle, RotateCcw, Trash2 } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  savedAt: string;
  source: "local" | "server";
  onRecover: () => void;
  onDiscard: () => void;
}

export function DraftRecoveryBanner({ savedAt, source, onRecover, onDiscard }: Props) {
  const timeAgo = formatTimeAgo(new Date(savedAt));
  
  return (
    <Alert variant="warning" className="mb-4">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Unsaved Draft Found</AlertTitle>
      <AlertDescription className="flex items-center justify-between">
        <span>
          Draft from {timeAgo} ({source === "local" ? "this browser" : "cloud"})
        </span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onDiscard}>
            <Trash2 className="h-4 w-4 mr-1" />
            Discard
          </Button>
          <Button variant="default" size="sm" onClick={onRecover}>
            <RotateCcw className="h-4 w-4 mr-1" />
            Recover
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
```

---

## 4. Backend API

### 4.1 Draft Endpoints

```python
# api/routes/drafts.py
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime

router = APIRouter(prefix="/api/documents")

@router.put("/{doc_hash}/draft")
async def save_draft(doc_hash: str, body: DraftRequest, request: Request):
    """Save draft to Firestore."""
    user = get_iap_user(request)
    
    db.collection("drafts").document(doc_hash).set({
        "doc_hash": doc_hash,
        "data": body.data,
        "saved_at": body.savedAt,
        "user_id": user["email"],
        "updated_at": datetime.utcnow()
    })
    
    return {"status": "saved"}


@router.get("/{doc_hash}/draft")
async def get_draft(doc_hash: str, request: Request):
    """Get draft from Firestore."""
    user = get_iap_user(request)
    
    doc = db.collection("drafts").document(doc_hash).get()
    
    if not doc.exists:
        raise HTTPException(404, "No draft found")
    
    draft = doc.to_dict()
    
    # Only return draft if same user or no user restriction
    if draft.get("user_id") and draft["user_id"] != user["email"]:
        raise HTTPException(403, "Draft belongs to another user")
    
    return draft


@router.delete("/{doc_hash}/draft")
async def delete_draft(doc_hash: str, request: Request):
    """Delete draft from Firestore."""
    db.collection("drafts").document(doc_hash).delete()
    return {"status": "deleted"}
```

---

## 5. Autosave Indicator UI

```tsx
// ui/components/AutosaveIndicator.tsx
import { Cloud, CloudOff, Loader2 } from "lucide-react";

interface Props {
  lastSaved: Date | null;
  saving: boolean;
  error: string | null;
}

export function AutosaveIndicator({ lastSaved, saving, error }: Props) {
  if (saving) {
    return (
      <div className="flex items-center gap-1 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Saving...
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="flex items-center gap-1 text-sm text-amber-600">
        <CloudOff className="h-4 w-4" />
        {error}
      </div>
    );
  }
  
  if (lastSaved) {
    return (
      <div className="flex items-center gap-1 text-sm text-green-600">
        <Cloud className="h-4 w-4" />
        Saved {formatTimeAgo(lastSaved)}
      </div>
    );
  }
  
  return null;
}
```

---

## 6. Cleanup Policy

Drafts are temporary. Auto-delete after document is processed:

```python
# Called after document approval
async def cleanup_draft(doc_hash: str):
    """Delete draft after successful processing."""
    db.collection("drafts").document(doc_hash).delete()
```

---

## 7. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Multiple tabs editing same doc | Each tab has own draft, last save wins |
| User A drafts, User B opens | User B cannot recover User A's draft |
| localStorage disabled | Firestore-only (slightly less reliable) |
| Firestore unavailable | localStorage-only (browser-local) |
| Draft older than current data | Don't prompt recovery |
