"""Schema Registry & Versioning.

This module defines all document schemas with version tracking and migration support.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from pydantic import BaseModel, Field

# ============================================================
# Migration Metadata
# ============================================================


@dataclass
class MigrationMetadata:
    """Tracks migration provenance for data quality."""

    is_migrated: bool = False
    source_version: str | None = None
    migrated_at: str | None = None
    fields_defaulted: list[str] = field(default_factory=list)


# ============================================================
# Schema Configuration
# ============================================================


@dataclass
class SchemaConfig:
    """Configuration for a document type's schemas."""

    versions: dict[str, type[BaseModel]]
    current: str
    deprecated: list[str]
    migrations: dict[str, Callable[[dict], dict]]


# ============================================================
# Exceptions
# ============================================================


class UnsupportedDocumentTypeError(Exception):
    """Raised when document_type is not in registry."""


class DeprecatedSchemaError(Exception):
    """Raised when attempting to use deprecated schema for new documents."""


# ============================================================
# Delivery Note Schemas
# ============================================================


class DeliveryNoteV1(BaseModel):
    """Version 1: Basic fields only."""

    schema_version: str = Field(default="v1", frozen=True)
    document_type: str = Field(default="delivery_note", frozen=True)
    management_id: str = Field(..., description="管理番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")


class DeliveryNoteV2(BaseModel):
    """Version 2: Added delivery date, payment due, amount."""

    schema_version: str = Field(default="v2", frozen=True)
    document_type: str = Field(default="delivery_note", frozen=True)
    management_id: str = Field(..., description="管理番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")
    delivery_date: date = Field(..., description="納品日")
    payment_due_date: date | None = Field(None, description="支払期限")
    total_amount: int = Field(..., description="合計金額", ge=0)

    # Migration tracking (excluded from validation)
    migration_metadata: MigrationMetadata | None = Field(default=None, exclude=True, repr=False)


# ============================================================
# Invoice Schemas
# ============================================================


class InvoiceV1(BaseModel):
    """Version 1: Basic invoice."""

    schema_version: str = Field(default="v1", frozen=True)
    document_type: str = Field(default="invoice", frozen=True)
    invoice_number: str = Field(..., description="請求書番号")
    company_name: str = Field(..., description="会社名")
    issue_date: date = Field(..., description="発行日")
    total_amount: int = Field(..., description="請求金額", ge=0)
    tax_amount: int = Field(..., description="消費税額", ge=0)


# ============================================================
# Migration Functions
# ============================================================


def migrate_delivery_note_v1_to_v2(data: dict) -> dict:
    """Migrate DeliveryNoteV1 to V2.

    Args:
        data: Dictionary containing V1 schema data

    Returns:
        Dictionary with V2 schema structure including migration metadata

    Notes:
        - delivery_date defaults to issue_date
        - total_amount defaults to 0
        - payment_due_date defaults to None
    """
    defaulted_fields: list[str] = []

    # Track fields being defaulted
    if "total_amount" not in data or data.get("total_amount") is None:
        defaulted_fields.append("total_amount")

    if "delivery_date" not in data:
        defaulted_fields.append("delivery_date")

    # Only count payment_due_date as defaulted if key is missing
    # (None is a valid explicit value)
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
        migrated["migration_metadata"] = {
            "is_migrated": True,
            "source_version": data.get("schema_version", "v1"),
            "migrated_at": datetime.utcnow().isoformat(),
            "fields_defaulted": defaulted_fields,
        }

    return migrated


# ============================================================
# Schema Registry
# ============================================================


SCHEMA_REGISTRY: dict[str, SchemaConfig] = {
    "delivery_note": SchemaConfig(
        versions={
            "v1": DeliveryNoteV1,
            "v2": DeliveryNoteV2,
        },
        current="v2",
        deprecated=["v1"],
        migrations={
            "v1": migrate_delivery_note_v1_to_v2,
        },
    ),
    "invoice": SchemaConfig(
        versions={
            "v1": InvoiceV1,
        },
        current="v1",
        deprecated=[],
        migrations={},
    ),
}


# ============================================================
# Registry Access Functions
# ============================================================


def get_schema(document_type: str, version: str | None = None) -> type[BaseModel]:
    """Retrieve schema class from registry.

    Args:
        document_type: Document type (e.g., "delivery_note", "invoice")
        version: Optional version string, defaults to current

    Returns:
        Pydantic model class for the specified schema

    Raises:
        UnsupportedDocumentTypeError: If document_type not found in registry
        ValueError: If version not found for document_type

    Examples:
        >>> schema = get_schema("delivery_note")  # Returns DeliveryNoteV2
        >>> schema = get_schema("delivery_note", "v1")  # Returns DeliveryNoteV1
    """
    if document_type not in SCHEMA_REGISTRY:
        available = list(SCHEMA_REGISTRY.keys())
        raise UnsupportedDocumentTypeError(
            f"Document type '{document_type}' not registered. Available types: {available}"
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


def validate_new_document(document_type: str, version: str) -> None:
    """Validate that new documents use current schema version.

    Called when processing new uploads — blocks deprecated versions.

    Args:
        document_type: Document type to validate
        version: Schema version to check

    Raises:
        UnsupportedDocumentTypeError: If document_type not found
        DeprecatedSchemaError: If version is deprecated
    """
    if document_type not in SCHEMA_REGISTRY:
        raise UnsupportedDocumentTypeError(f"Unknown document type: {document_type}")

    config = SCHEMA_REGISTRY[document_type]

    if version in config.deprecated:
        raise DeprecatedSchemaError(
            f"Schema '{document_type}/{version}' is deprecated for new documents. "
            f"Use current version: '{config.current}'"
        )


def migrate_data(document_type: str, data: dict) -> dict:
    """Dynamically migrate data to current schema version.

    Handles multi-step migrations (v1 → v2 → v3).

    Args:
        document_type: Document type to migrate
        data: Document data dictionary

    Returns:
        Migrated data dictionary with current schema version

    Raises:
        UnsupportedDocumentTypeError: If document_type not found
        ValueError: If no migration path exists
    """
    if document_type not in SCHEMA_REGISTRY:
        raise UnsupportedDocumentTypeError(f"Unknown document type: {document_type}")

    config = SCHEMA_REGISTRY[document_type]
    current_version = data.get("schema_version", "v1")

    # Already current
    if current_version == config.current:
        return data

    # Chain migrations
    all_defaulted: list[str] = []
    original_version = current_version

    while current_version != config.current:
        if current_version not in config.migrations:
            raise ValueError(
                f"No migration path from '{current_version}' to '{config.current}' "
                f"for document type '{document_type}'"
            )

        migration_fn = config.migrations[current_version]
        data = migration_fn(data)

        # Collect defaulted fields
        if "migration_metadata" in data:
            metadata = data["migration_metadata"]
            if isinstance(metadata, dict):
                all_defaulted.extend(metadata.get("fields_defaulted", []))

        current_version = data["schema_version"]

    # Final metadata
    if all_defaulted:
        data["migration_metadata"] = {
            "is_migrated": True,
            "source_version": original_version,
            "migrated_at": datetime.utcnow().isoformat(),
            "fields_defaulted": list(set(all_defaulted)),  # Dedupe
        }

    return data


def list_schemas() -> dict[str, dict]:
    """List all registered schemas with their versions.

    Useful for API documentation and debugging.

    Returns:
        Dictionary mapping document types to their schema information

    Examples:
        >>> schemas = list_schemas()
        >>> schemas["delivery_note"]
        {'current': 'v2', 'deprecated': ['v1'], 'versions': ['v1', 'v2']}
    """
    result = {}

    for doc_type, config in SCHEMA_REGISTRY.items():
        result[doc_type] = {
            "current": config.current,
            "deprecated": config.deprecated,
            "versions": list(config.versions.keys()),
        }

    return result


def generate_schema_description(schema_class: type[BaseModel]) -> str:
    """Generate human-readable schema description for Gemini prompts.

    Args:
        schema_class: Pydantic model class

    Returns:
        Markdown-formatted schema description

    Examples:
        >>> desc = generate_schema_description(DeliveryNoteV1)
        >>> print(desc)
        ## DeliveryNoteV1

        - **management_id** (required): 管理番号
          - Type: `<class 'str'>`
        ...
    """
    lines = [f"## {schema_class.__name__}", ""]

    for field_name, field_info in schema_class.model_fields.items():
        # Skip private fields and excluded fields
        if field_name.startswith("_") or field_info.exclude:
            continue

        required = "required" if field_info.is_required() else "optional"
        description = field_info.description or ""
        field_type = str(field_info.annotation)

        lines.append(f"- **{field_name}** ({required}): {description}")
        lines.append(f"  - Type: `{field_type}`")

        # Add constraints
        metadata = field_info.metadata
        for constraint in metadata:
            if hasattr(constraint, "ge") and constraint.ge is not None:
                lines.append(f"  - Minimum: {constraint.ge}")
            if hasattr(constraint, "le") and constraint.le is not None:
                lines.append(f"  - Maximum: {constraint.le}")

    return "\n".join(lines)
