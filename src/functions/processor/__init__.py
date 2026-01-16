"""
Document Processor Cloud Function.

Main entry point for the OCR pipeline that processes documents
uploaded to GCS.
"""

from src.functions.processor.main import process_document

__all__ = ["process_document"]
