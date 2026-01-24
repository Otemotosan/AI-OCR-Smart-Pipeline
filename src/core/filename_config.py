"""
Filename configuration module for dynamic filename generation.

This module provides functionality to load and apply filename templates
from a YAML configuration file stored in GCS. This enables:
- Dynamic field ordering in output filenames
- No redeployment required for config changes
- Future WebUI integration for config editing

See: docs/specs/05_schema.md for schema definitions
"""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from typing import Any

import yaml

from src.core.logging import get_logger

logger = get_logger(__name__)

# Default configuration when no external config is available
DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.0",
    "filename_templates": {
        "delivery_note": {
            "folder": "delivery_notes",
            "pattern": "{management_id}_{company_name}_{issue_date}",
            "fields": {
                "management_id": {"source": "management_id", "max_length": 30},
                "company_name": {"source": "company_name", "max_length": 30},
                "issue_date": {"source": "issue_date", "format": "%Y%m%d"},
            },
        },
        "order_form": {
            "folder": "order_forms",
            "pattern": "{order_number}_{supplier}_{order_date}",
            "fields": {
                "order_number": {"source": "order_number", "max_length": 30},
                "supplier": {
                    "source": ["supplier_company", "company_name"],
                    "max_length": 30,
                },
                "order_date": {
                    "source": ["order_date", "issue_date"],
                    "format": "%Y%m%d",
                },
            },
        },
        "invoice": {
            "folder": "invoices",
            "pattern": "{invoice_number}_{vendor}_{issue_date}",
            "fields": {
                "invoice_number": {"source": "invoice_number", "max_length": 30},
                "vendor": {
                    "source": ["vendor_name", "company_name"],
                    "max_length": 30,
                },
                "issue_date": {"source": "issue_date", "format": "%Y%m%d"},
            },
        },
        "generic": {
            "folder": "unknown",
            "use_original_filename": True,
        },
    },
}

# Environment variable for config bucket
CONFIG_BUCKET = os.getenv("CONFIG_BUCKET", "")
CONFIG_FILE_PATH = os.getenv("CONFIG_FILE_PATH", "config/filename_config.yaml")


class FilenameConfig:
    """Manages filename configuration loading and caching."""

    _instance: FilenameConfig | None = None
    _config: dict[str, Any] | None = None
    _loaded_at: datetime | None = None

    def __new__(cls) -> FilenameConfig:
        """Singleton pattern for config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_config(self, force_reload: bool = False) -> dict[str, Any]:
        """
        Load configuration from GCS or use defaults.

        Args:
            force_reload: Force reload from GCS even if cached

        Returns:
            Configuration dictionary
        """
        if self._config is not None and not force_reload:
            return self._config

        # Try to load from GCS if bucket is configured
        if CONFIG_BUCKET:
            try:
                self._config = self._load_from_gcs()
                self._loaded_at = datetime.utcnow()
                logger.info(
                    "config_loaded_from_gcs",
                    bucket=CONFIG_BUCKET,
                    path=CONFIG_FILE_PATH,
                )
                return self._config
            except Exception as e:
                logger.warning(
                    "config_load_failed_using_defaults",
                    error=str(e),
                    bucket=CONFIG_BUCKET,
                )

        # Use default config
        self._config = DEFAULT_CONFIG.copy()
        self._loaded_at = datetime.utcnow()
        logger.info("using_default_config")
        return self._config

    def _load_from_gcs(self) -> dict[str, Any]:
        """Load configuration from GCS bucket."""
        # Import here to avoid circular imports
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(CONFIG_BUCKET)
        blob = bucket.blob(CONFIG_FILE_PATH)

        content = blob.download_as_string().decode("utf-8")
        config = yaml.safe_load(content)

        # Validate config structure
        if "filename_templates" not in config:
            raise ValueError("Invalid config: missing 'filename_templates'")

        return config

    def get_template(self, document_type: str) -> dict[str, Any]:
        """
        Get filename template for a document type.

        Args:
            document_type: Type of document (delivery_note, order_form, etc.)

        Returns:
            Template configuration dictionary
        """
        config = self.load_config()
        templates = config.get("filename_templates", {})

        # Return specific template or generic fallback
        if document_type in templates:
            return templates[document_type]
        return templates.get("generic", DEFAULT_CONFIG["filename_templates"]["generic"])

    def reload(self) -> None:
        """Force reload configuration from source."""
        self._config = None
        self.load_config(force_reload=True)


@lru_cache(maxsize=1)
def get_config() -> FilenameConfig:
    """Get singleton FilenameConfig instance."""
    return FilenameConfig()


def generate_filename_from_template(
    schema_data: dict[str, Any],
    document_type: str,
    timestamp: datetime,
    original_filename: str | None = None,
) -> tuple[str, str]:
    """
    Generate filename and folder from template configuration.

    Args:
        schema_data: Extracted document data
        document_type: Type of document
        timestamp: Processing timestamp
        original_filename: Original source filename (for unknown documents)

    Returns:
        Tuple of (folder_name, filename)
    """
    config = get_config()
    template = config.get_template(document_type)

    folder = template.get("folder", "unknown")

    # Handle generic/unknown documents - use original filename
    if template.get("use_original_filename") and original_filename:
        base_name = (
            original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
        )
        filename = f"{_sanitize(base_name)}.pdf"
        return folder, filename

    # Build filename from pattern
    pattern = template.get("pattern", "{document_id}_{date}")
    fields = template.get("fields", {})

    values: dict[str, str] = {}
    for field_name, field_config in fields.items():
        value = _extract_field_value(schema_data, field_config, timestamp)
        values[field_name] = value

    try:
        filename = pattern.format(**values) + ".pdf"
    except KeyError as e:
        logger.warning("pattern_format_error", pattern=pattern, missing_key=str(e))
        # Fallback to simple naming
        doc_id = schema_data.get("document_id", "unknown")
        date_str = timestamp.strftime("%Y%m%d")
        filename = f"{_sanitize(str(doc_id))}_{date_str}.pdf"

    return folder, filename


def _extract_field_value(
    schema_data: dict[str, Any],
    field_config: dict[str, Any],
    timestamp: datetime,
) -> str:
    """Extract and format a field value from schema data."""
    source = field_config.get("source", "")
    max_length = field_config.get("max_length", 50)
    date_format = field_config.get("format")

    # Handle multiple source fields (fallback chain)
    if isinstance(source, list):
        for src in source:
            value = schema_data.get(src)
            if value:
                break
        else:
            value = None
    else:
        value = schema_data.get(source)

    if value is None:
        return "unknown"

    # Handle date formatting
    if date_format:
        value = _format_date(value, date_format, timestamp)
    else:
        value = str(value)

    return _sanitize(value, max_length)


def _format_date(
    value: Any,
    date_format: str,
    fallback_timestamp: datetime,
) -> str:
    """Format a date value to string."""
    if isinstance(value, datetime):
        return value.strftime(date_format)

    if isinstance(value, str):
        # Try parsing various date formats
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime(date_format)
            except ValueError:
                continue

        # If parsing fails, try to extract digits
        digits = "".join(filter(str.isdigit, value))
        if len(digits) >= 8:
            return digits[:8]

    if isinstance(value, int):
        return str(value)

    # Fallback to timestamp
    return fallback_timestamp.strftime(date_format)


def _sanitize(value: str, max_length: int = 50) -> str:
    """Sanitize string for use in filename."""
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*\x00'
    for char in invalid_chars:
        value = value.replace(char, "")

    # Replace whitespace with underscore
    value = "_".join(value.split())

    # Remove control characters
    value = "".join(c for c in value if ord(c) >= 32)

    # Truncate
    if len(value) > max_length:
        value = value[:max_length]

    # Clean up trailing underscores
    value = value.strip("_")

    return value or "unknown"
