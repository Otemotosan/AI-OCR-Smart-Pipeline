# Schema Registry & Versioning

**Spec ID**: 05  
**Status**: Final  
**Dependencies**: Pydantic v2

---

## 1. Design Philosophy

**Fail-Fast, Version-Aware**

- Unknown document types → immediate error (no silent defaults)
- Every record carries schema version
- Migration metadata tracks defaulted fields
- Read-time transformation for historical data

---

## 2. Registry Structure

### 2.1 Core Types

```python
# core/schemas.py
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from typing import Dict, Type, Callable, List, Optional
from datetime import date, datetime

@dataclass
class MigrationMetadata:
    """Tracks migration provenance for data quality."""
    is_migrated: bool = False
    source_version: Optional[str] = None
    migrated_at: Optional[str] = None
    fields_defaulted: List[str] = field(default_factory=list)

@dataclass
class SchemaConfig:
    """Configuration for a document type's schemas."""
    versions: Dict[str, Type[BaseModel]]
    current: str
    deprecated: List[str]
    migrations: Dict[str, Callable[[dict], dict]]
```

### 2.2 Schema Definitions

```python
# === Delivery Note Schemas ===

class DeliveryNoteV1(BaseModel):
    """Version 1: Basic fields only."""
    schema_version: str = "v1"
    document_type: str = "delivery_note"
    management_id: str = Field(..., description="管理番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")


class DeliveryNoteV2(BaseModel):
    """Version 2: Added delivery date, payment due, amount."""
    schema_version: str = "v2"
    document_type: str = "delivery_note"
    management_id: str = Field(..., description="管理番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")
    delivery_date: date = Field(..., description="納品日")
    payment_due_date: Optional[date] = Field(None, description="支払期限")
    total_amount: int = Field(..., description="合計金額", ge=0)
    
    # Migration tracking (optional, excluded from validation)
    _migration_metadata: Optional[MigrationMetadata] = None


# === Invoice Schemas ===

class InvoiceV1(BaseModel):
    """Version 1: Basic invoice."""
    schema_version: str = "v1"
    document_type: str = "invoice"
    invoice_number: str = Field(..., description="請求書番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")
    total_amount: int = Field(..., description="請求金額", ge=0)
    tax_amount: int = Field(..., description="消費税額", ge=0)
```

### 2.3 Registry Definition

```python
SCHEMA_REGISTRY: Dict[str, SchemaConfig] = {
    "delivery_note": SchemaConfig(
        versions={
            "v1": DeliveryNoteV1,
            "v2": DeliveryNoteV2,
        },
        current="v2",
        deprecated=["v1"],
        migrations={
            "v1": migrate_delivery_note_v1_to_v2,
        }
    ),
    "invoice": SchemaConfig(
        versions={
            "v1": InvoiceV1,
        },
        current="v1",
        deprecated=[],
        migrations={}
    ),
}
```

---

## 3. Migration Functions

### 3.1 Migration with Metadata

```python
def migrate_delivery_note_v1_to_v2(data: dict) -> dict:
    """
    Migrate DeliveryNoteV1 to V2.
    
    Tracks which fields were defaulted for human review.
    """
    defaulted_fields = []
    
    # Track fields being defaulted
    if "total_amount" not in data or data.get("total_amount") is None:
        defaulted_fields.append("total_amount")
    
    if "delivery_date" not in data:
        defaulted_fields.append("delivery_date")
    
    if "payment_due_date" not in data:
        defaulted_fields.append("payment_due_date")
    
    # Build migrated data
    migrated = {
        **data,
        "schema_version": "v2",
        "delivery_date": data.get("delivery_date", data.get("issue_date")),
        "payment_due_date": data.get("payment_due_date"),  # None is allowed
        "total_amount": data.get("total_amount", 0),
    }
    
    # Attach migration metadata
    if defaulted_fields:
        migrated["_migration_metadata"] = {
            "is_migrated": True,
            "source_version": data.get("schema_version", "v1"),
            "migrated_at": datetime.utcnow().isoformat(),
            "fields_defaulted": defaulted_fields
        }
    
    return migrated
```

### 3.2 Migration Chain

For multi-version jumps (v1 → v3), chain migrations:

```python
def migrate_data(document_type: str, data: dict) -> dict:
    """
    Dynamically migrate data to current schema version.
    
    Handles multi-step migrations (v1 → v2 → v3).
    """
    if document_type not in SCHEMA_REGISTRY:
        raise UnsupportedDocumentTypeError(f"Unknown: {document_type}")
    
    config = SCHEMA_REGISTRY[document_type]
    current_version = data.get("schema_version", "v1")
    
    # Already current
    if current_version == config.current:
        return data
    
    # Chain migrations
    all_defaulted = []
    original_version = current_version
    
    while current_version != config.current:
        if current_version not in config.migrations:
            raise ValueError(
                f"No migration path from '{current_version}' to '{config.current}'"
            )
        
        migration_fn = config.migrations[current_version]
        data = migration_fn(data)
        
        # Collect defaulted fields
        if "_migration_metadata" in data:
            all_defaulted.extend(data["_migration_metadata"].get("fields_defaulted", []))
        
        current_version = data["schema_version"]
    
    # Final metadata
    if all_defaulted:
        data["_migration_metadata"] = {
            "is_migrated": True,
            "source_version": original_version,
            "migrated_at": datetime.utcnow().isoformat(),
            "fields_defaulted": list(set(all_defaulted))  # Dedupe
        }
    
    return data
```

---

## 4. Registry Access Functions

### 4.1 Get Schema (Fail-Fast)

```python
class UnsupportedDocumentTypeError(Exception):
    """Raised when document_type is not in registry."""
    pass

class DeprecatedSchemaError(Exception):
    """Raised when attempting to use deprecated schema for new documents."""
    pass

def get_schema(document_type: str, version: str = None) -> Type[BaseModel]:
    """
    Retrieve schema class from registry.
    
    Args:
        document_type: e.g., "delivery_note"
        version: Optional version, defaults to current
        
    Returns:
        Pydantic model class
        
    Raises:
        UnsupportedDocumentTypeError: If document_type not found
    """
    if document_type not in SCHEMA_REGISTRY:
        available = list(SCHEMA_REGISTRY.keys())
        raise UnsupportedDocumentTypeError(
            f"Document type '{document_type}' not registered. "
            f"Available types: {available}"
        )
    
    config = SCHEMA_REGISTRY[document_type]
    target_version = version or config.current
    
    if target_version not in config.versions:
        available = list(config.versions.keys())
        raise ValueError(
            f"Version '{target_version}' not found for '{document_type}'. "
            f"Available: {available}"
        )
    
    return config.versions[target_version]
```

### 4.2 Validate New Document

```python
def validate_new_document(document_type: str, version: str) -> None:
    """
    Validate that new documents use current schema version.
    
    Called when processing new uploads — blocks deprecated versions.
    
    Raises:
        DeprecatedSchemaError: If version is deprecated
    """
    if document_type not in SCHEMA_REGISTRY:
        raise UnsupportedDocumentTypeError(f"Unknown: {document_type}")
    
    config = SCHEMA_REGISTRY[document_type]
    
    if version in config.deprecated:
        raise DeprecatedSchemaError(
            f"Schema '{document_type}/{version}' is deprecated for new documents. "
            f"Use current version: '{config.current}'"
        )
```

### 4.3 List Available Schemas

```python
def list_schemas() -> Dict[str, dict]:
    """
    List all registered schemas with their versions.
    
    Useful for API documentation and debugging.
    """
    result = {}
    
    for doc_type, config in SCHEMA_REGISTRY.items():
        result[doc_type] = {
            "current": config.current,
            "deprecated": config.deprecated,
            "versions": list(config.versions.keys())
        }
    
    return result
```

---

## 5. Schema Description for Prompts

```python
def generate_schema_description(schema_class: Type[BaseModel]) -> str:
    """
    Generate human-readable schema description for Gemini prompts.
    """
    lines = [f"## {schema_class.__name__}", ""]
    
    for field_name, field_info in schema_class.model_fields.items():
        if field_name.startswith("_"):
            continue  # Skip private fields
        
        required = "required" if field_info.is_required() else "optional"
        description = field_info.description or ""
        field_type = str(field_info.annotation)
        
        lines.append(f"- **{field_name}** ({required}): {description}")
        lines.append(f"  - Type: `{field_type}`")
        
        # Add constraints
        if hasattr(field_info, 'ge') and field_info.ge is not None:
            lines.append(f"  - Minimum: {field_info.ge}")
    
    return "\n".join(lines)
```

---

## 6. Migration Metadata in UI

### 6.1 React Component

```tsx
// components/MigrationWarning.tsx
import { AlertTriangle } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";

interface MigrationMetadata {
  is_migrated: boolean;
  source_version: string;
  migrated_at: string;
  fields_defaulted: string[];
}

interface Props {
  metadata?: MigrationMetadata;
}

export function MigrationWarning({ metadata }: Props) {
  if (!metadata?.is_migrated) {
    return null;
  }
  
  return (
    <Alert variant="warning" className="mb-4">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Migrated Data — Verification Required</AlertTitle>
      <AlertDescription>
        <p className="mb-2">
          This record was automatically migrated from schema{" "}
          <code className="bg-amber-100 px-1 rounded">{metadata.source_version}</code>
          {" "}on {new Date(metadata.migrated_at).toLocaleDateString()}.
        </p>
        
        <p className="font-medium mb-1">
          The following fields were defaulted and require verification:
        </p>
        
        <ul className="list-disc list-inside space-y-1">
          {metadata.fields_defaulted.map((field) => (
            <li key={field} className="text-amber-700 font-medium">
              {field}
              {field === "total_amount" && (
                <span className="text-amber-600 font-normal">
                  {" "}— defaulted to 0, may need correction
                </span>
              )}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
```

### 6.2 Field Highlighting

```tsx
// components/EditableField.tsx
interface Props {
  name: string;
  value: any;
  isDefaulted: boolean;
  onChange: (value: any) => void;
}

export function EditableField({ name, value, isDefaulted, onChange }: Props) {
  return (
    <div className={`p-3 rounded-lg ${isDefaulted ? "bg-amber-50 border-2 border-amber-300" : "bg-gray-50"}`}>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {name}
        {isDefaulted && (
          <span className="ml-2 text-xs text-amber-600 font-normal">
            ⚠️ Needs verification
          </span>
        )}
      </label>
      
      <input
        type="text"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full p-2 border rounded ${
          isDefaulted ? "border-amber-400 focus:ring-amber-500" : "border-gray-300"
        }`}
      />
    </div>
  );
}
```

---

## 7. BigQuery Schema

### 7.1 Table Design

```sql
CREATE TABLE `project.dataset.extracted_documents` (
  doc_hash STRING NOT NULL,
  document_type STRING NOT NULL,
  schema_version STRING NOT NULL,
  
  -- Core fields (denormalized for query performance)
  management_id STRING,
  company_name STRING,
  issue_date DATE,
  total_amount INT64,
  
  -- Full JSON for flexibility
  validated_json STRING,  -- JSON string
  
  -- Migration tracking
  is_migrated BOOL DEFAULT FALSE,
  migration_source_version STRING,
  migration_defaulted_fields ARRAY<STRING>,
  
  -- Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  processed_by STRING,  -- Cloud Function execution ID
  
  -- Partitioning
  _PARTITIONTIME TIMESTAMP
)
PARTITION BY DATE(_PARTITIONTIME)
CLUSTER BY document_type, company_name;
```

### 7.2 Migration Query

```sql
-- Find all migrated records needing review
SELECT
  doc_hash,
  document_type,
  migration_source_version,
  migration_defaulted_fields,
  company_name,
  issue_date
FROM `project.dataset.extracted_documents`
WHERE is_migrated = TRUE
  AND ARRAY_LENGTH(migration_defaulted_fields) > 0
ORDER BY created_at DESC;
```

---

## 8. Adding New Schemas

### 8.1 Checklist

1. [ ] Define new `BaseModel` class with all fields
2. [ ] Add to `versions` dict in `SchemaConfig`
3. [ ] Update `current` to new version
4. [ ] Add old version to `deprecated` list
5. [ ] Implement migration function from old → new
6. [ ] Add migration function to `migrations` dict
7. [ ] Update BigQuery schema (if denormalized fields change)
8. [ ] Update Gemini prompt schema description
9. [ ] Test migration with sample data
10. [ ] Deploy and monitor

### 8.2 Example: Adding V3

```python
class DeliveryNoteV3(BaseModel):
    """Version 3: Added tax breakdown."""
    schema_version: str = "v3"
    # ... existing V2 fields ...
    tax_rate: float = Field(..., description="税率", ge=0, le=1)
    tax_amount: int = Field(..., description="消費税額", ge=0)

def migrate_delivery_note_v2_to_v3(data: dict) -> dict:
    defaulted = []
    
    if "tax_rate" not in data:
        defaulted.append("tax_rate")
    if "tax_amount" not in data:
        defaulted.append("tax_amount")
    
    return {
        **data,
        "schema_version": "v3",
        "tax_rate": data.get("tax_rate", 0.10),  # Default 10%
        "tax_amount": data.get("tax_amount", 0),
        "_migration_metadata": {
            "is_migrated": True,
            "source_version": data.get("schema_version", "v2"),
            "migrated_at": datetime.utcnow().isoformat(),
            "fields_defaulted": defaulted
        } if defaulted else None
    }

# Update registry
SCHEMA_REGISTRY["delivery_note"] = SchemaConfig(
    versions={"v1": V1, "v2": V2, "v3": V3},
    current="v3",
    deprecated=["v1", "v2"],
    migrations={
        "v1": migrate_v1_to_v2,
        "v2": migrate_v2_to_v3,
    }
)
```
