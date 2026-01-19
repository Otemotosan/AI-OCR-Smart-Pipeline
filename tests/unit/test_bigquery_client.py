"""Unit tests for BigQuery Client."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from core.bigquery_client import (
    CORRECTIONS_SCHEMA,
    EXTRACTION_RESULTS_SCHEMA,
    BigQueryClient,
    BigQueryConfig,
    BigQueryError,
    GoogleAPIError,
)


# ============================================================
# BigQueryConfig Tests
# ============================================================


class TestBigQueryConfig:
    """Tests for BigQueryConfig dataclass."""

    def test_config_creation(self) -> None:
        """Test basic config creation."""
        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )
        assert config.project_id == "test-project"
        assert config.dataset_id == "test_dataset"
        assert config.extractions_table == "extraction_results"
        assert config.corrections_table == "corrections"

    def test_config_custom_tables(self) -> None:
        """Test config with custom table names."""
        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
            extractions_table="custom_extractions",
            corrections_table="custom_corrections",
        )
        assert config.extractions_table == "custom_extractions"
        assert config.corrections_table == "custom_corrections"

    def test_extractions_table_id(self) -> None:
        """Test extractions table ID property."""
        config = BigQueryConfig(
            project_id="my-project",
            dataset_id="my_dataset",
            extractions_table="results",
        )
        assert config.extractions_table_id == "my-project.my_dataset.results"

    def test_corrections_table_id(self) -> None:
        """Test corrections table ID property."""
        config = BigQueryConfig(
            project_id="my-project",
            dataset_id="my_dataset",
            corrections_table="audit",
        )
        assert config.corrections_table_id == "my-project.my_dataset.audit"


# ============================================================
# Schema Tests
# ============================================================


class TestSchemas:
    """Tests for BigQuery schema definitions."""

    def test_extraction_schema_has_required_fields(self) -> None:
        """Test that extraction schema has all required fields."""
        field_names = {field.name for field in EXTRACTION_RESULTS_SCHEMA}
        required_fields = {
            "document_id",
            "document_type",
            "schema_version",
            "management_id",
            "company_name",
            "document_date",
            "issue_date",
            "extracted_data",
            "confidence_score",
            "model_used",
            "attempts_count",
            "processing_duration_ms",
            "source_uri",
            "destination_uri",
            "quality_warnings",
            "processed_at",
            "created_at",
        }
        assert required_fields.issubset(field_names)

    def test_corrections_schema_has_required_fields(self) -> None:
        """Test that corrections schema has all required fields."""
        field_names = {field.name for field in CORRECTIONS_SCHEMA}
        required_fields = {
            "correction_id",
            "document_id",
            "user_id",
            "field_name",
            "before_value",
            "after_value",
            "before_data",
            "after_data",
            "correction_type",
            "corrected_at",
        }
        assert required_fields.issubset(field_names)

    def test_extraction_schema_partition_field_exists(self) -> None:
        """Test that document_date exists for partitioning."""
        field_names = {field.name for field in EXTRACTION_RESULTS_SCHEMA}
        assert "document_date" in field_names

    def test_corrections_schema_partition_field_exists(self) -> None:
        """Test that corrected_at exists for partitioning."""
        field_names = {field.name for field in CORRECTIONS_SCHEMA}
        assert "corrected_at" in field_names


# ============================================================
# BigQueryClient Initialization Tests
# ============================================================


class TestBigQueryClientInit:
    """Tests for BigQueryClient initialization."""

    def test_init_with_config(self) -> None:
        """Test client initialization with config."""
        mock_bq_client = MagicMock()
        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        assert client.config == config
        assert client.client == mock_bq_client

    def test_client_property(self) -> None:
        """Test client property returns underlying client."""
        mock_bq_client = MagicMock()
        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        assert client.client is mock_bq_client


# ============================================================
# ensure_tables_exist Tests
# ============================================================


class TestEnsureTablesExist:
    """Tests for ensure_tables_exist method."""

    def test_ensure_tables_creates_both_tables(self) -> None:
        """Test that ensure_tables_exist creates both tables."""
        mock_bq_client = MagicMock()
        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.ensure_tables_exist()

        # Should call create_table twice
        assert mock_bq_client.create_table.call_count == 2

    def test_ensure_extractions_table_handles_error(self) -> None:
        """Test that extractions table creation handles errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.create_table.side_effect = GoogleAPIError("Test error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.ensure_tables_exist()

        assert "Failed to create extractions table" in str(exc_info.value)


# ============================================================
# insert_extraction Tests
# ============================================================


class TestInsertExtraction:
    """Tests for insert_extraction method."""

    def test_insert_extraction_success(self) -> None:
        """Test successful extraction insertion."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []  # No errors

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={"management_id": "DN-001", "company_name": "Test Co"},
            source_uri="gs://bucket/source.pdf",
            destination_uri="gs://bucket/dest.pdf",
            confidence_score=0.95,
            model_used="flash",
            attempts_count=1,
            processing_duration_ms=1500,
            quality_warnings=["missing_address"],
        )

        mock_bq_client.insert_rows_json.assert_called_once()
        call_args = mock_bq_client.insert_rows_json.call_args
        assert call_args[0][0] == "test-project.test_dataset.extraction_results"

    def test_insert_extraction_with_date_string(self) -> None:
        """Test extraction insertion with date string."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": "2024-01-15",
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] == "2024-01-15"
        assert row["issue_date"] == "2024-01-15"

    def test_insert_extraction_with_date_object(self) -> None:
        """Test extraction insertion with date object."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": date(2024, 1, 15),
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] == "2024-01-15"

    def test_insert_extraction_with_datetime_object(self) -> None:
        """Test extraction insertion with datetime object."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] == "2024-01-15"

    def test_insert_extraction_with_slash_date_format(self) -> None:
        """Test extraction insertion with slash date format."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": "2024/01/15",
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] == "2024-01-15"

    def test_insert_extraction_with_compact_date_format(self) -> None:
        """Test extraction insertion with compact date format."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": "20240115",
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] == "2024-01-15"

    def test_insert_extraction_with_invalid_date(self) -> None:
        """Test extraction insertion handles invalid date gracefully."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        # Should not raise even with invalid date
        client.insert_extraction(
            document_id="sha256:abc123",
            document_type="delivery_note",
            schema_version="v1",
            extracted_data={
                "management_id": "DN-001",
                "issue_date": "invalid-date",
            },
            source_uri="gs://bucket/source.pdf",
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["document_date"] is None

    def test_insert_extraction_with_errors(self) -> None:
        """Test extraction insertion with BigQuery errors."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = [{"errors": ["Test error"]}]

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.insert_extraction(
                document_id="sha256:abc123",
                document_type="delivery_note",
                schema_version="v1",
                extracted_data={"management_id": "DN-001"},
                source_uri="gs://bucket/source.pdf",
            )

        assert "BigQuery insertion errors" in str(exc_info.value)

    def test_insert_extraction_api_error(self) -> None:
        """Test extraction insertion handles API errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.side_effect = GoogleAPIError("API error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.insert_extraction(
                document_id="sha256:abc123",
                document_type="delivery_note",
                schema_version="v1",
                extracted_data={"management_id": "DN-001"},
                source_uri="gs://bucket/source.pdf",
            )

        assert "Failed to insert extraction" in str(exc_info.value)


# ============================================================
# insert_correction Tests
# ============================================================


class TestInsertCorrection:
    """Tests for insert_correction method."""

    def test_insert_correction_success(self) -> None:
        """Test successful correction insertion."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_correction(
            document_id="sha256:abc123",
            user_id="user@example.com",
            before_data={"management_id": "DN-001"},
            after_data={"management_id": "DN-002"},
            field_name="management_id",
            correction_type="field_edit",
        )

        mock_bq_client.insert_rows_json.assert_called_once()
        call_args = mock_bq_client.insert_rows_json.call_args
        assert call_args[0][0] == "test-project.test_dataset.corrections"
        row = call_args[0][1][0]
        assert row["document_id"] == "sha256:abc123"
        assert row["user_id"] == "user@example.com"
        assert row["field_name"] == "management_id"
        assert row["before_value"] == "DN-001"
        assert row["after_value"] == "DN-002"

    def test_insert_correction_bulk_edit(self) -> None:
        """Test correction insertion for bulk edit."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = []

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.insert_correction(
            document_id="sha256:abc123",
            user_id="user@example.com",
            before_data={"management_id": "DN-001", "company_name": "Old Co"},
            after_data={"management_id": "DN-002", "company_name": "New Co"},
        )

        call_args = mock_bq_client.insert_rows_json.call_args
        row = call_args[0][1][0]
        assert row["correction_type"] == "bulk_edit"
        assert row["field_name"] is None

    def test_insert_correction_with_errors(self) -> None:
        """Test correction insertion with BigQuery errors."""
        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.return_value = [{"errors": ["Test error"]}]

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.insert_correction(
                document_id="sha256:abc123",
                user_id="user@example.com",
                before_data={},
                after_data={},
            )

        assert "BigQuery correction insertion errors" in str(exc_info.value)

    def test_insert_correction_api_error(self) -> None:
        """Test correction insertion handles API errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.insert_rows_json.side_effect = GoogleAPIError("API error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.insert_correction(
                document_id="sha256:abc123",
                user_id="user@example.com",
                before_data={},
                after_data={},
            )

        assert "Failed to insert correction" in str(exc_info.value)


# ============================================================
# query_by_date_range Tests
# ============================================================


class TestQueryByDateRange:
    """Tests for query_by_date_range method."""

    def test_query_by_date_range_success(self) -> None:
        """Test successful date range query."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_row = MagicMock()
        mock_row.items.return_value = [("document_id", "sha256:abc123")]
        mock_row.keys.return_value = ["document_id"]
        mock_row.__iter__ = lambda self: iter([("document_id", "sha256:abc123")])
        mock_query_job.result.return_value = [mock_row]
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        results = client.query_by_date_range(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        mock_bq_client.query.assert_called_once()
        assert len(results) == 1

    def test_query_by_date_range_with_document_type(self) -> None:
        """Test date range query with document type filter."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        client.query_by_date_range(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            document_type="delivery_note",
        )

        # Check that query includes document_type filter
        call_args = mock_bq_client.query.call_args
        query = call_args[0][0]
        assert "document_type = @document_type" in query

    def test_query_by_date_range_api_error(self) -> None:
        """Test date range query handles API errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.query.side_effect = GoogleAPIError("API error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.query_by_date_range(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

        assert "Failed to query extractions" in str(exc_info.value)


# ============================================================
# get_processing_stats Tests
# ============================================================


class TestGetProcessingStats:
    """Tests for get_processing_stats method."""

    def test_get_processing_stats_success(self) -> None:
        """Test successful stats retrieval."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_row = MagicMock()
        mock_row.total_documents = 100
        mock_row.flash_count = 90
        mock_row.pro_count = 10
        mock_row.avg_attempts = 1.5
        mock_row.avg_confidence = 0.92
        mock_row.avg_duration_ms = 1500.0
        mock_query_job.result.return_value = [mock_row]
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        stats = client.get_processing_stats(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert stats["total_documents"] == 100
        assert stats["flash_count"] == 90
        assert stats["pro_count"] == 10
        assert stats["avg_attempts"] == 1.5
        assert stats["avg_confidence"] == 0.92
        assert stats["avg_duration_ms"] == 1500.0

    def test_get_processing_stats_empty_results(self) -> None:
        """Test stats retrieval with no results."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        stats = client.get_processing_stats(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert stats["total_documents"] == 0
        assert stats["flash_count"] == 0
        assert stats["pro_count"] == 0

    def test_get_processing_stats_null_values(self) -> None:
        """Test stats retrieval with null values."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_row = MagicMock()
        mock_row.total_documents = None
        mock_row.flash_count = None
        mock_row.pro_count = None
        mock_row.avg_attempts = None
        mock_row.avg_confidence = None
        mock_row.avg_duration_ms = None
        mock_query_job.result.return_value = [mock_row]
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        stats = client.get_processing_stats(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert stats["total_documents"] == 0
        assert stats["avg_attempts"] == 0

    def test_get_processing_stats_api_error(self) -> None:
        """Test stats retrieval handles API errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.query.side_effect = GoogleAPIError("API error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.get_processing_stats(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

        assert "Failed to get processing stats" in str(exc_info.value)


# ============================================================
# get_corrections_for_document Tests
# ============================================================


class TestGetCorrectionsForDocument:
    """Tests for get_corrections_for_document method."""

    def test_get_corrections_success(self) -> None:
        """Test successful corrections retrieval."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_row = MagicMock()
        mock_row.items.return_value = [("correction_id", "uuid-123")]
        mock_row.keys.return_value = ["correction_id"]
        mock_row.__iter__ = lambda self: iter([("correction_id", "uuid-123")])
        mock_query_job.result.return_value = [mock_row]
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        results = client.get_corrections_for_document("sha256:abc123")

        mock_bq_client.query.assert_called_once()
        assert len(results) == 1

    def test_get_corrections_empty(self) -> None:
        """Test corrections retrieval with no results."""
        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_bq_client.query.return_value = mock_query_job

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)
        results = client.get_corrections_for_document("sha256:nonexistent")

        assert results == []

    def test_get_corrections_api_error(self) -> None:
        """Test corrections retrieval handles API errors."""
        # GoogleAPIError imported from core.bigquery_client

        mock_bq_client = MagicMock()
        mock_bq_client.query.side_effect = GoogleAPIError("API error")

        config = BigQueryConfig(
            project_id="test-project",
            dataset_id="test_dataset",
        )

        client = BigQueryClient(config, client=mock_bq_client)

        with pytest.raises(BigQueryError) as exc_info:
            client.get_corrections_for_document("sha256:abc123")

        assert "Failed to get corrections" in str(exc_info.value)


# ============================================================
# BigQueryError Tests
# ============================================================


class TestBigQueryError:
    """Tests for BigQueryError exception."""

    def test_error_creation(self) -> None:
        """Test BigQueryError can be created."""
        error = BigQueryError("Test error message")
        assert str(error) == "Test error message"

    def test_error_is_exception(self) -> None:
        """Test BigQueryError is an Exception."""
        error = BigQueryError("Test")
        assert isinstance(error, Exception)
