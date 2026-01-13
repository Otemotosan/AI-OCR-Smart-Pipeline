"""Unit tests for schema registry and versioning."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from core.schemas import (
    SCHEMA_REGISTRY,
    DeliveryNoteV1,
    DeliveryNoteV2,
    DeprecatedSchemaError,
    InvoiceV1,
    MigrationMetadata,
    SchemaConfig,
    UnsupportedDocumentTypeError,
    generate_schema_description,
    get_schema,
    list_schemas,
    migrate_data,
    migrate_delivery_note_v1_to_v2,
    validate_new_document,
)

# ============================================================
# Schema Validation Tests
# ============================================================


class TestDeliveryNoteV1:
    """Test DeliveryNoteV1 schema validation."""

    def test_valid_delivery_note_v1(self) -> None:
        """Test creating valid DeliveryNoteV1 instance."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
        }
        doc = DeliveryNoteV1(**data)

        assert doc.schema_version == "v1"
        assert doc.document_type == "delivery_note"
        assert doc.management_id == "ABC123"
        assert doc.company_name == "テスト株式会社"
        assert doc.issue_date == date(2025, 1, 13)

    def test_missing_required_field(self) -> None:
        """Test validation error when required field missing."""
        data = {
            "management_id": "ABC123",
            # missing company_name
            "issue_date": date(2025, 1, 13),
        }
        with pytest.raises(ValidationError) as exc_info:
            DeliveryNoteV1(**data)

        assert "company_name" in str(exc_info.value)

    def test_invalid_date_type(self) -> None:
        """Test validation error for invalid date type."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "not-a-date",
        }
        with pytest.raises(ValidationError) as exc_info:
            DeliveryNoteV1(**data)

        assert "issue_date" in str(exc_info.value)


class TestDeliveryNoteV2:
    """Test DeliveryNoteV2 schema validation."""

    def test_valid_delivery_note_v2(self) -> None:
        """Test creating valid DeliveryNoteV2 instance."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
            "delivery_date": date(2025, 1, 15),
            "payment_due_date": date(2025, 2, 13),
            "total_amount": 10000,
        }
        doc = DeliveryNoteV2(**data)

        assert doc.schema_version == "v2"
        assert doc.document_type == "delivery_note"
        assert doc.total_amount == 10000
        assert doc.delivery_date == date(2025, 1, 15)
        assert doc.payment_due_date == date(2025, 2, 13)

    def test_optional_payment_due_date(self) -> None:
        """Test that payment_due_date is optional."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
            "delivery_date": date(2025, 1, 15),
            "payment_due_date": None,
            "total_amount": 10000,
        }
        doc = DeliveryNoteV2(**data)

        assert doc.payment_due_date is None

    def test_negative_amount_rejected(self) -> None:
        """Test validation error for negative total_amount."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
            "delivery_date": date(2025, 1, 15),
            "total_amount": -100,
        }
        with pytest.raises(ValidationError) as exc_info:
            DeliveryNoteV2(**data)

        assert "total_amount" in str(exc_info.value)


class TestInvoiceV1:
    """Test InvoiceV1 schema validation."""

    def test_valid_invoice_v1(self) -> None:
        """Test creating valid InvoiceV1 instance."""
        data = {
            "invoice_number": "INV-2025-001",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
            "total_amount": 11000,
            "tax_amount": 1000,
        }
        doc = InvoiceV1(**data)

        assert doc.schema_version == "v1"
        assert doc.document_type == "invoice"
        assert doc.invoice_number == "INV-2025-001"
        assert doc.total_amount == 11000
        assert doc.tax_amount == 1000

    def test_negative_tax_rejected(self) -> None:
        """Test validation error for negative tax_amount."""
        data = {
            "invoice_number": "INV-2025-001",
            "company_name": "テスト株式会社",
            "issue_date": date(2025, 1, 13),
            "total_amount": 11000,
            "tax_amount": -100,
        }
        with pytest.raises(ValidationError) as exc_info:
            InvoiceV1(**data)

        assert "tax_amount" in str(exc_info.value)


# ============================================================
# Registry Lookup Tests
# ============================================================


class TestGetSchema:
    """Test get_schema function."""

    def test_get_current_schema(self) -> None:
        """Test getting current schema version."""
        schema = get_schema("delivery_note")

        assert schema == DeliveryNoteV2

    def test_get_specific_version(self) -> None:
        """Test getting specific schema version."""
        schema = get_schema("delivery_note", "v1")

        assert schema == DeliveryNoteV1

    def test_get_invoice_schema(self) -> None:
        """Test getting invoice schema."""
        schema = get_schema("invoice")

        assert schema == InvoiceV1

    def test_unsupported_document_type(self) -> None:
        """Test error for unsupported document type."""
        with pytest.raises(UnsupportedDocumentTypeError) as exc_info:
            get_schema("unknown_type")

        assert "unknown_type" in str(exc_info.value)
        assert "Available types" in str(exc_info.value)

    def test_invalid_version(self) -> None:
        """Test error for invalid version."""
        with pytest.raises(ValueError) as exc_info:
            get_schema("delivery_note", "v99")

        assert "v99" in str(exc_info.value)
        assert "Available" in str(exc_info.value)


class TestValidateNewDocument:
    """Test validate_new_document function."""

    def test_current_version_allowed(self) -> None:
        """Test that current version is allowed."""
        # Should not raise
        validate_new_document("delivery_note", "v2")
        validate_new_document("invoice", "v1")

    def test_deprecated_version_rejected(self) -> None:
        """Test that deprecated version is rejected."""
        with pytest.raises(DeprecatedSchemaError) as exc_info:
            validate_new_document("delivery_note", "v1")

        assert "deprecated" in str(exc_info.value).lower()
        assert "v2" in str(exc_info.value)

    def test_unknown_document_type(self) -> None:
        """Test error for unknown document type."""
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_new_document("unknown", "v1")


# ============================================================
# Migration Tests
# ============================================================


class TestDeliveryNoteV1ToV2Migration:
    """Test delivery note v1 to v2 migration."""

    def test_migration_with_all_fields(self) -> None:
        """Test migration when all new fields provided."""
        v1_data = {
            "schema_version": "v1",
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
            "delivery_date": "2025-01-15",
            "payment_due_date": None,  # Explicitly provided as None
            "total_amount": 10000,
        }
        v2_data = migrate_delivery_note_v1_to_v2(v1_data)

        assert v2_data["schema_version"] == "v2"
        assert v2_data["delivery_date"] == "2025-01-15"
        assert v2_data["payment_due_date"] is None
        assert v2_data["total_amount"] == 10000
        assert "migration_metadata" not in v2_data  # No defaults needed

    def test_migration_with_defaults(self) -> None:
        """Test migration with defaulted fields."""
        v1_data = {
            "schema_version": "v1",
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
        }
        v2_data = migrate_delivery_note_v1_to_v2(v1_data)

        assert v2_data["schema_version"] == "v2"
        assert v2_data["delivery_date"] == "2025-01-13"  # Defaults to issue_date
        assert v2_data["total_amount"] == 0  # Defaults to 0
        assert v2_data["payment_due_date"] is None

        # Check migration metadata
        metadata = v2_data["migration_metadata"]
        assert metadata["is_migrated"] is True
        assert metadata["source_version"] == "v1"
        assert "total_amount" in metadata["fields_defaulted"]
        assert "delivery_date" in metadata["fields_defaulted"]
        assert "payment_due_date" in metadata["fields_defaulted"]

    def test_migration_partial_defaults(self) -> None:
        """Test migration with some fields provided."""
        v1_data = {
            "schema_version": "v1",
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
            "total_amount": 5000,
        }
        v2_data = migrate_delivery_note_v1_to_v2(v1_data)

        metadata = v2_data["migration_metadata"]
        assert "total_amount" not in metadata["fields_defaulted"]
        assert "delivery_date" in metadata["fields_defaulted"]


class TestMigrateData:
    """Test migrate_data function."""

    def test_already_current_version(self) -> None:
        """Test that current version data is returned unchanged."""
        v2_data = {
            "schema_version": "v2",
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
            "delivery_date": "2025-01-15",
            "total_amount": 10000,
        }
        result = migrate_data("delivery_note", v2_data)

        assert result == v2_data

    def test_migrate_v1_to_current(self) -> None:
        """Test migrating v1 to current version."""
        v1_data = {
            "schema_version": "v1",
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
        }
        result = migrate_data("delivery_note", v1_data)

        assert result["schema_version"] == "v2"
        assert "migration_metadata" in result

    def test_missing_schema_version_defaults_to_v1(self) -> None:
        """Test that missing schema_version defaults to v1."""
        data = {
            "management_id": "ABC123",
            "company_name": "テスト株式会社",
            "issue_date": "2025-01-13",
        }
        result = migrate_data("delivery_note", data)

        assert result["schema_version"] == "v2"

    def test_unknown_document_type(self) -> None:
        """Test error for unknown document type."""
        with pytest.raises(UnsupportedDocumentTypeError):
            migrate_data("unknown", {})

    def test_no_migration_path(self) -> None:
        """Test error when no migration path exists."""
        # Invoice has no migrations (only v1)
        data = {"schema_version": "v0"}

        with pytest.raises(ValueError) as exc_info:
            migrate_data("invoice", data)

        assert "No migration path" in str(exc_info.value)


# ============================================================
# Utility Function Tests
# ============================================================


class TestListSchemas:
    """Test list_schemas function."""

    def test_list_all_schemas(self) -> None:
        """Test listing all registered schemas."""
        schemas = list_schemas()

        assert "delivery_note" in schemas
        assert "invoice" in schemas

        delivery_note = schemas["delivery_note"]
        assert delivery_note["current"] == "v2"
        assert delivery_note["deprecated"] == ["v1"]
        assert "v1" in delivery_note["versions"]
        assert "v2" in delivery_note["versions"]

        invoice = schemas["invoice"]
        assert invoice["current"] == "v1"
        assert invoice["deprecated"] == []


class TestGenerateSchemaDescription:
    """Test generate_schema_description function."""

    def test_generate_delivery_note_v1_description(self) -> None:
        """Test generating schema description."""
        description = generate_schema_description(DeliveryNoteV1)

        assert "DeliveryNoteV1" in description
        assert "management_id" in description
        assert "管理番号" in description
        assert "required" in description

    def test_generate_invoice_v1_description(self) -> None:
        """Test generating invoice schema description."""
        description = generate_schema_description(InvoiceV1)

        assert "InvoiceV1" in description
        assert "invoice_number" in description
        assert "請求書番号" in description

    def test_private_fields_excluded(self) -> None:
        """Test that private fields are excluded from description."""
        description = generate_schema_description(DeliveryNoteV2)

        assert "migration_metadata" not in description


# ============================================================
# Schema Registry Tests
# ============================================================


class TestSchemaRegistry:
    """Test SCHEMA_REGISTRY structure."""

    def test_registry_structure(self) -> None:
        """Test that registry has expected structure."""
        assert isinstance(SCHEMA_REGISTRY, dict)
        assert "delivery_note" in SCHEMA_REGISTRY
        assert "invoice" in SCHEMA_REGISTRY

    def test_delivery_note_config(self) -> None:
        """Test delivery note schema config."""
        config = SCHEMA_REGISTRY["delivery_note"]

        assert isinstance(config, SchemaConfig)
        assert config.current == "v2"
        assert "v1" in config.deprecated
        assert "v1" in config.versions
        assert "v2" in config.versions
        assert "v1" in config.migrations

    def test_invoice_config(self) -> None:
        """Test invoice schema config."""
        config = SCHEMA_REGISTRY["invoice"]

        assert isinstance(config, SchemaConfig)
        assert config.current == "v1"
        assert config.deprecated == []
        assert "v1" in config.versions
        assert config.migrations == {}


# ============================================================
# MigrationMetadata Tests
# ============================================================


class TestMigrationMetadata:
    """Test MigrationMetadata dataclass."""

    def test_default_values(self) -> None:
        """Test default values for MigrationMetadata."""
        metadata = MigrationMetadata()

        assert metadata.is_migrated is False
        assert metadata.source_version is None
        assert metadata.migrated_at is None
        assert metadata.fields_defaulted == []

    def test_with_values(self) -> None:
        """Test MigrationMetadata with custom values."""
        metadata = MigrationMetadata(
            is_migrated=True,
            source_version="v1",
            migrated_at="2025-01-13T10:00:00",
            fields_defaulted=["total_amount", "delivery_date"],
        )

        assert metadata.is_migrated is True
        assert metadata.source_version == "v1"
        assert metadata.migrated_at == "2025-01-13T10:00:00"
        assert len(metadata.fields_defaulted) == 2
