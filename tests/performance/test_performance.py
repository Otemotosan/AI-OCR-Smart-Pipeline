"""Performance tests for AI-OCR Smart Pipeline.

Tests validate performance requirements from docs/specs/07_monitoring.md:
- Processing latency: p50 < 10s, p99 < 60s
- Success rate: >95%
- Pro escalation rate: <20%
"""

from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import pytest
from src.core.linters.gate import GateLinter
from src.core.linters.quality import QualityLinter
from src.core.schemas import SCHEMA_REGISTRY, DeliveryNoteV1


def json_serializer(obj: Any) -> str:
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class TestValidationPerformance:
    """Test validation performance under load."""

    @pytest.fixture
    def valid_delivery_note(self) -> dict[str, Any]:
        """Valid delivery note data."""
        return {
            "document_type": "delivery_note",
            "schema_version": "v1",
            "management_id": "DN-2025-001234",
            "company_name": "株式会社山田商事",
            "issue_date": "2025-01-15",
            "confidence": 0.95,
        }

    @pytest.fixture
    def valid_invoice(self) -> dict[str, Any]:
        """Valid invoice data."""
        return {
            "document_type": "invoice",
            "schema_version": "v1",
            "invoice_number": "INV-2025-005678",
            "company_name": "田中電機株式会社",
            "issue_date": "2025-01-15",
            "total_amount": 123456,
            "tax_amount": 12345,
            "confidence": 0.92,
        }

    def test_gate_linter_latency_single(self, valid_delivery_note: dict[str, Any]) -> None:
        """Gate linter should complete in <100ms for single validation."""
        linter = GateLinter()

        start = time.perf_counter()
        result = linter.validate(valid_delivery_note)
        duration_ms = (time.perf_counter() - start) * 1000

        assert result.passed
        assert duration_ms < 100, f"Gate linter took {duration_ms:.2f}ms, expected <100ms"

    def test_quality_linter_latency_single(self, valid_delivery_note: dict[str, Any]) -> None:
        """Quality linter should complete in <100ms for single validation."""
        linter = QualityLinter()

        start = time.perf_counter()
        _result = linter.validate(valid_delivery_note)
        duration_ms = (time.perf_counter() - start) * 1000

        assert duration_ms < 100, f"Quality linter took {duration_ms:.2f}ms, expected <100ms"

    def test_gate_linter_batch_performance(self, valid_delivery_note: dict[str, Any]) -> None:
        """Gate linter should handle 100 documents in <1s."""
        linter = GateLinter()
        documents = [valid_delivery_note.copy() for _ in range(100)]

        start = time.perf_counter()
        results = [linter.validate(doc) for doc in documents]
        duration_ms = (time.perf_counter() - start) * 1000

        assert all(r.passed for r in results)
        assert duration_ms < 1000, f"Batch validation took {duration_ms:.2f}ms, expected <1000ms"

    def test_combined_linter_latency(
        self, valid_delivery_note: dict[str, Any], valid_invoice: dict[str, Any]
    ) -> None:
        """Combined validation should complete in <200ms."""
        gate_linter = GateLinter()
        quality_linter = QualityLinter()

        documents = [valid_delivery_note, valid_invoice]
        durations = []

        for doc in documents:
            start = time.perf_counter()
            _gate_result = gate_linter.validate(doc)
            _quality_result = quality_linter.validate(doc)
            duration_ms = (time.perf_counter() - start) * 1000
            durations.append(duration_ms)

        avg_duration = statistics.mean(durations)
        max_duration = max(durations)

        assert avg_duration < 200, f"Average validation took {avg_duration:.2f}ms, expected <200ms"
        assert max_duration < 500, f"Max validation took {max_duration:.2f}ms, expected <500ms"


class TestSchemaPerformance:
    """Test schema operations performance."""

    def test_schema_parsing_latency(self) -> None:
        """Schema parsing should complete in <50ms."""
        data = {
            "document_type": "delivery_note",
            "schema_version": "v1",
            "management_id": "DN-2025-001234",
            "company_name": "株式会社テスト",
            "issue_date": "2025-01-15",
        }

        start = time.perf_counter()
        schema = DeliveryNoteV1.model_validate(data)
        duration_ms = (time.perf_counter() - start) * 1000

        assert schema is not None
        assert duration_ms < 50, f"Schema parsing took {duration_ms:.2f}ms, expected <50ms"

    def test_schema_serialization_latency(self) -> None:
        """Schema serialization should complete in <50ms."""
        schema = DeliveryNoteV1(
            management_id="DN-2025-001234",
            company_name="株式会社テスト",
            issue_date="2025-01-15",
        )

        start = time.perf_counter()
        data = schema.model_dump()
        json_str = json.dumps(data, ensure_ascii=False, default=json_serializer)
        duration_ms = (time.perf_counter() - start) * 1000

        assert len(json_str) > 0
        assert duration_ms < 50, f"Serialization took {duration_ms:.2f}ms, expected <50ms"

    def test_schema_registry_lookup(self) -> None:
        """Schema registry lookup should complete in <1ms."""
        iterations = 1000

        start = time.perf_counter()
        for _ in range(iterations):
            config = SCHEMA_REGISTRY.get("delivery_note")
            if config:
                _ = config.versions.get("1")
        duration_ms = (time.perf_counter() - start) * 1000

        avg_duration_us = (duration_ms / iterations) * 1000  # microseconds
        assert (
            avg_duration_us < 100
        ), f"Registry lookup took {avg_duration_us:.2f}μs, expected <100μs"


class TestConcurrentOperations:
    """Test concurrent operation performance."""

    @pytest.fixture
    def sample_documents(self) -> list[dict[str, Any]]:
        """Generate sample documents for testing."""
        documents = []
        for i in range(50):
            if i % 2 == 0:
                documents.append(
                    {
                        "document_type": "delivery_note",
                        "schema_version": "v1",
                        "management_id": f"DN-2025-{i:06d}",
                        "company_name": f"テスト会社{i}",
                        "issue_date": "2025-01-15",
                        "confidence": 0.9 + (i % 10) / 100,
                    }
                )
            else:
                documents.append(
                    {
                        "document_type": "invoice",
                        "schema_version": "v1",
                        "invoice_number": f"INV-2025-{i:06d}",
                        "company_name": f"テスト株式会社{i}",
                        "issue_date": "2025-01-15",
                        "total_amount": 10000 * i,
                        "tax_amount": 1000 * i,
                        "confidence": 0.85 + (i % 15) / 100,
                    }
                )
        return documents

    def test_concurrent_validation(self, sample_documents: list[dict[str, Any]]) -> None:
        """Concurrent validation should complete within reasonable time."""

        def validate_document(doc: dict[str, Any]) -> float:
            gate = GateLinter()
            quality = QualityLinter()

            start = time.perf_counter()
            gate.validate(doc)
            quality.validate(doc)
            return (time.perf_counter() - start) * 1000

        # Concurrent with 4 workers
        concurrent_start = time.perf_counter()
        concurrent_durations = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(validate_document, doc) for doc in sample_documents]
            for future in as_completed(futures):
                concurrent_durations.append(future.result())
        concurrent_total = (time.perf_counter() - concurrent_start) * 1000

        # Should complete all 50 docs in under 2 seconds
        assert (
            concurrent_total < 2000
        ), f"Concurrent validation took {concurrent_total:.0f}ms, expected <2000ms"
        # Average per-document latency should be reasonable
        avg_duration = statistics.mean(concurrent_durations)
        assert avg_duration < 50, f"Average per-doc latency {avg_duration:.2f}ms exceeds 50ms"

    def test_memory_stability_under_load(self, sample_documents: list[dict[str, Any]]) -> None:
        """Memory usage should remain stable under repeated operations."""

        gate = GateLinter()
        quality = QualityLinter()

        # Track object counts
        initial_count = len([obj for obj in gc_get_objects() if isinstance(obj, dict)])

        # Run 1000 validations
        for _ in range(20):
            for doc in sample_documents:
                gate.validate(doc)
                quality.validate(doc)

        # Check object count hasn't grown excessively
        final_count = len([obj for obj in gc_get_objects() if isinstance(obj, dict)])
        growth = final_count - initial_count

        # Allow for some object creation but not unbounded growth
        # 1000 iterations should not create more than 5000 persistent objects
        assert growth < 5000, f"Object count grew by {growth}, potential memory leak"


def gc_get_objects() -> list:
    """Get all tracked objects (helper for memory tests)."""
    import gc

    return gc.get_objects()


class TestLatencyDistribution:
    """Test latency distribution metrics."""

    def test_validation_latency_percentiles(self) -> None:
        """Validation latency should meet p50/p95/p99 targets."""
        gate = GateLinter()
        quality = QualityLinter()

        documents = []
        for i in range(100):
            if i % 2 == 0:
                documents.append(
                    {
                        "document_type": "delivery_note",
                        "schema_version": "v1",
                        "management_id": f"DN-2025-{i:06d}",
                        "company_name": f"会社名{i}",
                        "issue_date": "2025-01-15",
                        "confidence": 0.9,
                    }
                )
            else:
                documents.append(
                    {
                        "document_type": "invoice",
                        "schema_version": "v1",
                        "invoice_number": f"INV-2025-{i:06d}",
                        "company_name": f"会社名{i}",
                        "issue_date": "2025-01-15",
                        "total_amount": 10000,
                        "tax_amount": 1000,
                        "confidence": 0.9,
                    }
                )

        durations = []
        for doc in documents:
            start = time.perf_counter()
            gate.validate(doc)
            quality.validate(doc)
            durations.append((time.perf_counter() - start) * 1000)

        durations.sort()
        p50 = durations[49]
        p95 = durations[94]
        p99 = durations[98]

        # Validation-only targets (not full pipeline)
        assert p50 < 10, f"p50 latency {p50:.2f}ms exceeds 10ms target"
        assert p95 < 50, f"p95 latency {p95:.2f}ms exceeds 50ms target"
        assert p99 < 100, f"p99 latency {p99:.2f}ms exceeds 100ms target"


class TestThroughput:
    """Test throughput capabilities."""

    def test_validation_throughput(self) -> None:
        """Should validate at least 100 documents per second."""
        gate = GateLinter()
        quality = QualityLinter()

        documents = [
            {
                "document_type": "delivery_note",
                "schema_version": 1,
                "management_id": f"DN-2025-{i:06d}",
                "company_name": f"テスト会社{i}",
                "issue_date": "2025-01-15",
                "confidence": 0.95,
            }
            for i in range(200)
        ]

        start = time.perf_counter()
        for doc in documents:
            gate.validate(doc)
            quality.validate(doc)
        duration = time.perf_counter() - start

        throughput = len(documents) / duration
        assert throughput >= 100, f"Throughput {throughput:.1f} docs/sec below 100 target"

    def test_schema_parsing_throughput(self) -> None:
        """Should parse at least 500 schemas per second."""
        data = {
            "document_type": "delivery_note",
            "schema_version": "v1",
            "management_id": "DN-2025-001234",
            "company_name": "株式会社テスト",
            "issue_date": "2025-01-15",
        }

        iterations = 500
        start = time.perf_counter()
        for _ in range(iterations):
            DeliveryNoteV1.model_validate(data)
        duration = time.perf_counter() - start

        throughput = iterations / duration
        assert throughput >= 500, f"Throughput {throughput:.1f} parses/sec below 500 target"


class TestResourceEfficiency:
    """Test resource usage efficiency."""

    def test_json_serialization_size(self) -> None:
        """Serialized document should be reasonably sized."""
        schema = DeliveryNoteV1(
            management_id="DN-2025-001234",
            company_name="株式会社山田商事テスト用長い会社名",
            issue_date="2025-01-15",
        )

        json_str = json.dumps(schema.model_dump(), ensure_ascii=False, default=json_serializer)
        size_bytes = len(json_str.encode("utf-8"))

        # Document JSON should be under 1KB for simple delivery notes
        assert size_bytes < 1024, f"JSON size {size_bytes} bytes exceeds 1KB limit"

    def test_validation_result_size(self) -> None:
        """Validation results should be compact."""
        gate = GateLinter()

        # Test with failing document to get full error output
        invalid_doc = {
            "document_type": "delivery_note",
            "schema_version": 1,
            "management_id": "bad",  # Invalid
            "company_name": "",  # Invalid
            "issue_date": "2099-01-01",  # Invalid future date
            "confidence": 0.5,
        }

        result = gate.validate(invalid_doc)
        json_str = json.dumps({"passed": result.passed, "errors": result.errors})
        size_bytes = len(json_str.encode("utf-8"))

        # Error details should stay under 2KB even with multiple errors
        assert size_bytes < 2048, f"Error JSON size {size_bytes} bytes exceeds 2KB limit"


class TestStressConditions:
    """Test behavior under stress conditions."""

    def test_large_batch_stability(self) -> None:
        """System should handle large batches without degradation."""
        gate = GateLinter()
        quality = QualityLinter()

        batch_sizes = [10, 100, 500]
        avg_latencies = {}

        for batch_size in batch_sizes:
            documents = [
                {
                    "document_type": "delivery_note",
                    "schema_version": 1,
                    "management_id": f"DN-2025-{i:06d}",
                    "company_name": f"テスト会社{i}",
                    "issue_date": "2025-01-15",
                    "confidence": 0.95,
                }
                for i in range(batch_size)
            ]

            start = time.perf_counter()
            for doc in documents:
                gate.validate(doc)
                quality.validate(doc)
            total_duration = (time.perf_counter() - start) * 1000

            avg_latencies[batch_size] = total_duration / batch_size

        # Average latency should not increase significantly with batch size
        latency_10 = avg_latencies[10]
        latency_500 = avg_latencies[500]
        degradation = latency_500 / latency_10

        assert degradation < 2.0, f"Latency degraded {degradation:.1f}x at larger batch sizes"

    def test_rapid_successive_calls(self) -> None:
        """System should handle rapid successive calls."""
        gate = GateLinter()

        doc = {
            "document_type": "delivery_note",
            "schema_version": 1,
            "management_id": "DN-2025-001234",
            "company_name": "株式会社テスト",
            "issue_date": "2025-01-15",
            "confidence": 0.95,
        }

        # 1000 rapid calls
        errors = 0
        for _ in range(1000):
            try:
                result = gate.validate(doc)
                if not result.passed:
                    errors += 1
            except Exception:
                errors += 1

        # All calls should succeed without error
        assert errors == 0, f"{errors} errors during rapid successive calls"


class TestIntegrationBenchmarks:
    """Integration benchmarks simulating real workloads."""

    def test_mixed_document_workload(self) -> None:
        """Simulate mixed document processing workload."""
        gate = GateLinter()
        quality = QualityLinter()

        # 70% delivery notes, 30% invoices (typical mix)
        workload = []
        for i in range(70):
            workload.append(
                {
                    "document_type": "delivery_note",
                    "schema_version": "v1",
                    "management_id": f"DN-2025-{i:06d}",
                    "company_name": f"配送会社{i}",
                    "issue_date": "2025-01-15",
                    "confidence": 0.9 + (i % 10) / 100,
                }
            )
        for i in range(30):
            workload.append(
                {
                    "document_type": "invoice",
                    "schema_version": "v1",
                    "invoice_number": f"INV-2025-{i:06d}",  # Invoice uses invoice_number
                    "company_name": f"請求会社{i}",
                    "issue_date": "2025-01-15",
                    "total_amount": 10000 * (i + 1),
                    "tax_amount": 1000 * (i + 1),
                    "confidence": 0.85 + (i % 15) / 100,
                }
            )

        success_count = 0
        total_duration = 0.0

        for doc in workload:
            start = time.perf_counter()
            gate_result = gate.validate(doc)
            quality.validate(doc)
            total_duration += (time.perf_counter() - start) * 1000

            if gate_result.passed:
                success_count += 1

        success_rate = success_count / len(workload)
        avg_latency = total_duration / len(workload)

        # Success rate should be 100% for valid test data
        assert success_rate == 1.0, f"Success rate {success_rate:.1%} below 100%"
        # Average latency should be under 20ms per document
        assert avg_latency < 20, f"Average latency {avg_latency:.2f}ms exceeds 20ms target"

    def test_error_recovery_performance(self) -> None:
        """Test performance when handling errors."""
        gate = GateLinter()

        # Mix of valid and invalid documents
        documents = []
        for i in range(50):
            if i % 5 == 0:  # 20% invalid
                documents.append(
                    {
                        "document_type": "delivery_note",
                        "schema_version": 1,
                        "management_id": "bad",  # Invalid
                        "company_name": "",  # Invalid
                        "issue_date": "2099-01-01",  # Invalid
                        "confidence": 0.3,
                    }
                )
            else:
                documents.append(
                    {
                        "document_type": "delivery_note",
                        "schema_version": 1,
                        "management_id": f"DN-2025-{i:06d}",
                        "company_name": f"会社{i}",
                        "issue_date": "2025-01-15",
                        "confidence": 0.95,
                    }
                )

        start = time.perf_counter()
        for doc in documents:
            gate.validate(doc)
        total_duration = (time.perf_counter() - start) * 1000

        avg_latency = total_duration / len(documents)

        # Error handling should not significantly impact performance
        assert avg_latency < 30, f"Average latency {avg_latency:.2f}ms with errors exceeds 30ms"
