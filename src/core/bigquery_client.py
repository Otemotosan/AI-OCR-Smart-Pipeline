"""
BigQuery Client for Analytics.

Handles insertion of extraction results and corrections for
analytics and reporting purposes.

See: docs/specs/07_monitoring.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from google.api_core.exceptions import GoogleAPIError
    from google.cloud import bigquery
else:
    try:
        from google.api_core.exceptions import GoogleAPIError
        from google.cloud import bigquery
    except ImportError:
        # Mock for testing without google-cloud-bigquery installed
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        class GoogleAPIError(Exception):  # type: ignore[no-redef]
            """Mock GoogleAPIError for testing."""

        bigquery = SimpleNamespace()  # type: ignore[assignment]
        bigquery.Client = MagicMock
        bigquery.Table = MagicMock
        bigquery.TimePartitioning = MagicMock
        bigquery.TimePartitioningType = SimpleNamespace(DAY="DAY")
        bigquery.QueryJobConfig = MagicMock
        bigquery.ScalarQueryParameter = MagicMock
        bigquery.SchemaField = lambda name, type_, mode="NULLABLE": SimpleNamespace(
            name=name, field_type=type_, mode=mode
        )

logger = structlog.get_logger(__name__)


class BigQueryError(Exception):
    """Base exception for BigQuery operations."""

    pass


@dataclass
class BigQueryConfig:
    """
    BigQuery configuration.

    Attributes:
        project_id: GCP project ID
        dataset_id: BigQuery dataset ID
        extractions_table: Table for extraction results
        corrections_table: Table for correction audit trail
    """

    project_id: str
    dataset_id: str
    extractions_table: str = "extraction_results"
    corrections_table: str = "corrections"

    @property
    def extractions_table_id(self) -> str:
        """Full table ID for extractions."""
        return f"{self.project_id}.{self.dataset_id}.{self.extractions_table}"

    @property
    def corrections_table_id(self) -> str:
        """Full table ID for corrections."""
        return f"{self.project_id}.{self.dataset_id}.{self.corrections_table}"


# Schema definitions for BigQuery tables
EXTRACTION_RESULTS_SCHEMA = [
    bigquery.SchemaField("document_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("document_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("schema_version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("management_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("company_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("document_date", "DATE", mode="NULLABLE"),  # Partition key
    bigquery.SchemaField("issue_date", "DATE", mode="NULLABLE"),
    bigquery.SchemaField("extracted_data", "JSON", mode="NULLABLE"),
    bigquery.SchemaField("confidence_score", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("model_used", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("attempts_count", "INT64", mode="NULLABLE"),
    bigquery.SchemaField("processing_duration_ms", "INT64", mode="NULLABLE"),
    bigquery.SchemaField("source_uri", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("destination_uri", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("quality_warnings", "STRING", mode="REPEATED"),
    bigquery.SchemaField("processed_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

CORRECTIONS_SCHEMA = [
    bigquery.SchemaField("correction_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("document_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("field_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("before_value", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("after_value", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("before_data", "JSON", mode="NULLABLE"),
    bigquery.SchemaField("after_data", "JSON", mode="NULLABLE"),
    bigquery.SchemaField("correction_type", "STRING", mode="NULLABLE"),  # field_edit, bulk_edit
    bigquery.SchemaField("corrected_at", "TIMESTAMP", mode="REQUIRED"),
]


class BigQueryClient:
    """
    High-level BigQuery client for analytics operations.

    Handles insertion of extraction results and corrections,
    as well as analytics queries.
    """

    def __init__(
        self,
        config: BigQueryConfig,
        client: bigquery.Client | None = None,
    ) -> None:
        """
        Initialize BigQuery client.

        Args:
            config: BigQuery configuration
            client: Optional BigQuery client. If not provided, creates a new one.
        """
        self.config = config
        self._client = client or bigquery.Client(project=config.project_id)

    @property
    def client(self) -> bigquery.Client:
        """Get the underlying BigQuery client."""
        return self._client

    def ensure_tables_exist(self) -> None:
        """
        Ensure required tables exist with proper schema.

        Creates tables if they don't exist, with appropriate
        partitioning and clustering.
        """
        self._ensure_extractions_table()
        self._ensure_corrections_table()

    def _ensure_extractions_table(self) -> None:
        """Create extractions table if it doesn't exist."""
        table_ref = bigquery.Table(
            self.config.extractions_table_id,
            schema=EXTRACTION_RESULTS_SCHEMA,
        )

        # Configure partitioning by document_date
        table_ref.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="document_date",
        )

        # Configure clustering by document_type
        table_ref.clustering_fields = ["document_type"]

        try:
            self._client.create_table(table_ref, exists_ok=True)
            logger.info(
                "bigquery_table_ensured",
                table=self.config.extractions_table_id,
            )
        except GoogleAPIError as e:
            logger.error(
                "bigquery_table_create_failed",
                table=self.config.extractions_table_id,
                error=str(e),
            )
            raise BigQueryError(f"Failed to create extractions table: {e}") from e

    def _ensure_corrections_table(self) -> None:
        """Create corrections table if it doesn't exist."""
        table_ref = bigquery.Table(
            self.config.corrections_table_id,
            schema=CORRECTIONS_SCHEMA,
        )

        # Partition by corrected_at timestamp
        table_ref.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="corrected_at",
        )

        try:
            self._client.create_table(table_ref, exists_ok=True)
            logger.info(
                "bigquery_table_ensured",
                table=self.config.corrections_table_id,
            )
        except GoogleAPIError as e:
            logger.error(
                "bigquery_table_create_failed",
                table=self.config.corrections_table_id,
                error=str(e),
            )
            raise BigQueryError(f"Failed to create corrections table: {e}") from e

    def insert_extraction(
        self,
        document_id: str,
        document_type: str,
        schema_version: str,
        extracted_data: dict[str, Any],
        source_uri: str,
        destination_uri: str | None = None,
        confidence_score: float | None = None,
        model_used: str | None = None,
        attempts_count: int | None = None,
        processing_duration_ms: int | None = None,
        quality_warnings: list[str] | None = None,
    ) -> None:
        """
        Insert an extraction result into BigQuery.

        Args:
            document_id: Document hash
            document_type: Type of document (delivery_note, invoice, etc.)
            schema_version: Schema version string
            extracted_data: Full extracted data
            source_uri: Source GCS URI
            destination_uri: Destination GCS URI (after processing)
            confidence_score: OCR confidence score
            model_used: Model used for extraction (flash/pro)
            attempts_count: Number of extraction attempts
            processing_duration_ms: Total processing time in milliseconds
            quality_warnings: List of quality warning messages

        Raises:
            BigQueryError: If insertion fails
        """
        now = datetime.now(UTC)

        # Extract key fields from extracted_data
        management_id = extracted_data.get("management_id")
        company_name = extracted_data.get("company_name")
        issue_date_str = extracted_data.get("issue_date")

        # Parse issue_date for partitioning
        document_date = None
        issue_date = None
        if issue_date_str:
            try:
                if isinstance(issue_date_str, str):
                    # Handle various date formats
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
                        try:
                            parsed = datetime.strptime(issue_date_str, fmt)
                            document_date = parsed.date().isoformat()
                            issue_date = parsed.date().isoformat()
                            break
                        except ValueError:
                            continue
                elif isinstance(issue_date_str, (datetime, date)):
                    if isinstance(issue_date_str, datetime):
                        document_date = issue_date_str.date().isoformat()
                        issue_date = issue_date_str.date().isoformat()
                    else:
                        document_date = issue_date_str.isoformat()
                        issue_date = issue_date_str.isoformat()
            except Exception as e:
                logger.warning(
                    "bigquery_date_parse_failed",
                    issue_date=issue_date_str,
                    error=str(e),
                )

        # Build row for insertion
        row = {
            "document_id": document_id,
            "document_type": document_type,
            "schema_version": schema_version,
            "management_id": management_id,
            "company_name": company_name,
            "document_date": document_date,
            "issue_date": issue_date,
            "extracted_data": extracted_data,
            "confidence_score": confidence_score,
            "model_used": model_used,
            "attempts_count": attempts_count,
            "processing_duration_ms": processing_duration_ms,
            "source_uri": source_uri,
            "destination_uri": destination_uri,
            "quality_warnings": quality_warnings or [],
            "processed_at": now.isoformat(),
            "created_at": now.isoformat(),
        }

        try:
            errors = self._client.insert_rows_json(
                self.config.extractions_table_id,
                [row],
            )

            if errors:
                logger.error(
                    "bigquery_insert_errors",
                    table=self.config.extractions_table_id,
                    errors=errors,
                )
                raise BigQueryError(f"BigQuery insertion errors: {errors}")

            logger.info(
                "bigquery_extraction_inserted",
                document_id=document_id,
                document_type=document_type,
            )

        except GoogleAPIError as e:
            logger.error(
                "bigquery_extraction_insert_failed",
                document_id=document_id,
                error=str(e),
            )
            raise BigQueryError(f"Failed to insert extraction: {e}") from e

    def insert_correction(
        self,
        document_id: str,
        user_id: str,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        field_name: str | None = None,
        correction_type: str = "bulk_edit",
    ) -> None:
        """
        Insert a correction record into BigQuery.

        This creates an append-only audit trail of all corrections.

        Args:
            document_id: Document hash
            user_id: User who made the correction
            before_data: Data before correction
            after_data: Data after correction
            field_name: Specific field that was corrected (for single-field edits)
            correction_type: Type of correction (field_edit, bulk_edit)

        Raises:
            BigQueryError: If insertion fails
        """
        import uuid

        now = datetime.now(UTC)
        correction_id = str(uuid.uuid4())

        # Extract before/after values for single-field edits
        before_value = None
        after_value = None
        if field_name:
            before_value = str(before_data.get(field_name, ""))
            after_value = str(after_data.get(field_name, ""))

        row = {
            "correction_id": correction_id,
            "document_id": document_id,
            "user_id": user_id,
            "field_name": field_name,
            "before_value": before_value,
            "after_value": after_value,
            "before_data": before_data,
            "after_data": after_data,
            "correction_type": correction_type,
            "corrected_at": now.isoformat(),
        }

        try:
            errors = self._client.insert_rows_json(
                self.config.corrections_table_id,
                [row],
            )

            if errors:
                logger.error(
                    "bigquery_correction_insert_errors",
                    errors=errors,
                )
                raise BigQueryError(f"BigQuery correction insertion errors: {errors}")

            logger.info(
                "bigquery_correction_inserted",
                document_id=document_id,
                user_id=user_id,
                correction_id=correction_id,
            )

        except GoogleAPIError as e:
            logger.error(
                "bigquery_correction_insert_failed",
                document_id=document_id,
                error=str(e),
            )
            raise BigQueryError(f"Failed to insert correction: {e}") from e

    def query_by_date_range(
        self,
        start_date: date,
        end_date: date,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query extraction results by date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            document_type: Optional document type filter

        Returns:
            List of extraction result dictionaries

        Raises:
            BigQueryError: If query fails
        """
        # Table names from config, not user input - safe from SQL injection
        query = f"""
            SELECT *
            FROM `{self.config.extractions_table_id}`
            WHERE document_date BETWEEN @start_date AND @end_date
        """  # nosec B608 # noqa: S608

        if document_type:
            query += " AND document_type = @document_type"

        query += " ORDER BY processed_at DESC"

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
            ]
            + (
                [bigquery.ScalarQueryParameter("document_type", "STRING", document_type)]
                if document_type
                else []
            )
        )

        try:
            query_job = self._client.query(query, job_config=job_config)
            results = list(query_job.result())

            return [dict(row) for row in results]

        except GoogleAPIError as e:
            logger.error(
                "bigquery_query_failed",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                error=str(e),
            )
            raise BigQueryError(f"Failed to query extractions: {e}") from e

    def get_processing_stats(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """
        Get processing statistics for a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Dictionary with statistics:
            - total_documents: Total number of documents
            - by_type: Count by document type
            - by_model: Count by model used
            - avg_attempts: Average number of attempts
            - avg_confidence: Average confidence score
            - avg_duration_ms: Average processing duration
        """
        # Table names from config, not user input - safe from SQL injection
        query = f"""
            SELECT
                COUNT(*) as total_documents,
                COUNTIF(model_used = 'flash') as flash_count,
                COUNTIF(model_used = 'pro') as pro_count,
                AVG(attempts_count) as avg_attempts,
                AVG(confidence_score) as avg_confidence,
                AVG(processing_duration_ms) as avg_duration_ms
            FROM `{self.config.extractions_table_id}`
            WHERE document_date BETWEEN @start_date AND @end_date
        """  # nosec B608 # noqa: S608

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
            ]
        )

        try:
            query_job = self._client.query(query, job_config=job_config)
            results = list(query_job.result())

            if not results:
                return {
                    "total_documents": 0,
                    "flash_count": 0,
                    "pro_count": 0,
                    "avg_attempts": 0,
                    "avg_confidence": 0,
                    "avg_duration_ms": 0,
                }

            row = results[0]
            return {
                "total_documents": row.total_documents or 0,
                "flash_count": row.flash_count or 0,
                "pro_count": row.pro_count or 0,
                "avg_attempts": float(row.avg_attempts or 0),
                "avg_confidence": float(row.avg_confidence or 0),
                "avg_duration_ms": float(row.avg_duration_ms or 0),
            }

        except GoogleAPIError as e:
            logger.error(
                "bigquery_stats_query_failed",
                error=str(e),
            )
            raise BigQueryError(f"Failed to get processing stats: {e}") from e

    def get_corrections_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """
        Get all corrections for a specific document.

        Args:
            document_id: Document hash

        Returns:
            List of correction records, ordered by corrected_at
        """
        # Table names from config, not user input - safe from SQL injection
        query = f"""
            SELECT *
            FROM `{self.config.corrections_table_id}`
            WHERE document_id = @document_id
            ORDER BY corrected_at ASC
        """  # nosec B608 # noqa: S608

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("document_id", "STRING", document_id),
            ]
        )

        try:
            query_job = self._client.query(query, job_config=job_config)
            results = list(query_job.result())

            return [dict(row) for row in results]

        except GoogleAPIError as e:
            logger.error(
                "bigquery_corrections_query_failed",
                document_id=document_id,
                error=str(e),
            )
            raise BigQueryError(f"Failed to get corrections: {e}") from e
