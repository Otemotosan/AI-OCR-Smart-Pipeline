"""Integration tests for full extraction pipeline.

Tests the complete flow:
Document AI → Gemini API → Gate Linter → Schema Validation

Measures:
- Success rate (target: ≥90%)
- Average cost per document (target: <¥2)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.extraction import ExtractionResult, GeminiInput, extract_with_retry
from core.linters.gate import GateLinter
from core.schemas import DeliveryNoteV2, InvoiceV1


# ============================================================
# Test Data
# ============================================================


class TestDocument:
    """Test document with expected results."""

    def __init__(
        self,
        name: str,
        markdown: str,
        expected_schema_class: type,
        expected_data: dict,
        confidence: float = 0.95,
    ):
        self.name = name
        self.markdown = markdown
        self.expected_schema_class = expected_schema_class
        self.expected_data = expected_data
        self.confidence = confidence


# Sample test documents
TEST_DOCUMENTS = [
    TestDocument(
        name="delivery_note_high_confidence",
        markdown="""# 納品書

管理番号: DN-2025-001
会社名: 株式会社テスト商事
発行日: 2025年1月10日
納品日: 2025年1月10日

商品一覧:
- 商品A: ¥10,000
- 商品B: ¥5,000

合計: ¥15,000
""",
        expected_schema_class=DeliveryNoteV2,
        expected_data={
            "document_type": "delivery_note",
            "management_id": "DN-2025-001",
            "company_name": "株式会社テスト商事",
            "issue_date": "2025-01-10",
            "delivery_date": "2025-01-10",
            "total_amount": 15000,
        },
        confidence=0.95,
    ),
    TestDocument(
        name="invoice_high_confidence",
        markdown="""# 請求書

請求書番号: INV-2025-001
会社名: サンプル株式会社
発行日: 2025年1月15日

請求金額: ¥50,000
消費税: ¥5,000
""",
        expected_schema_class=InvoiceV1,
        expected_data={
            "document_type": "invoice",
            "invoice_number": "INV-2025-001",
            "company_name": "サンプル株式会社",
            "issue_date": "2025-01-15",
            "total_amount": 50000,
            "tax_amount": 5000,
        },
        confidence=0.96,
    ),
    TestDocument(
        name="delivery_note_low_confidence",
        markdown="""# 納品書 (FAX)

管理番号: DN-2025-002
会社名: 低品質株式会社
発行日: 2025年1月12日
納品日: 2025年1月12日

合計: ¥20,000
""",
        expected_schema_class=DeliveryNoteV2,
        expected_data={
            "document_type": "delivery_note",
            "management_id": "DN-2025-002",
            "company_name": "低品質株式会社",
            "issue_date": "2025-01-12",
            "delivery_date": "2025-01-12",
            "total_amount": 20000,
        },
        confidence=0.75,  # Low confidence triggers image attachment
    ),
    TestDocument(
        name="invoice_complex",
        markdown="""# 請求書

株式会社複雑商事 御中

請求書番号: INV-2025-002
発行日: 2025-01-20

---

明細:
1. サービスA: ¥30,000
2. サービスB: ¥20,000

小計: ¥50,000
消費税: ¥5,000
合計: ¥55,000
""",
        expected_schema_class=InvoiceV1,
        expected_data={
            "document_type": "invoice",
            "invoice_number": "INV-2025-002",
            "company_name": "株式会社複雑商事",
            "issue_date": "2025-01-20",
            "total_amount": 55000,
            "tax_amount": 5000,
        },
        confidence=0.92,
    ),
    TestDocument(
        name="delivery_note_with_special_chars",
        markdown="""# 納品書

管理番号: DN-2025-003
会社名: 特殊文字株式会社 (東京)
発行日: 2025年1月25日
納品日: 2025年1月26日

合計: ¥30,000
※ 配送先: 〒100-0001 東京都千代田区
""",
        expected_schema_class=DeliveryNoteV2,
        expected_data={
            "document_type": "delivery_note",
            "management_id": "DN-2025-003",
            "company_name": "特殊文字株式会社 (東京)",
            "issue_date": "2025-01-25",
            "delivery_date": "2025-01-26",
            "total_amount": 30000,
        },
        confidence=0.89,
    ),
]


# ============================================================
# Integration Tests
# ============================================================


class TestExtractionPipeline:
    """Integration tests for full extraction pipeline."""

    def test_end_to_end_delivery_note_success(self) -> None:
        """Test successful end-to-end extraction for delivery note."""
        test_doc = TEST_DOCUMENTS[0]  # High confidence delivery note

        # Create GeminiInput
        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
            reason=None,
        )

        # Mock GeminiClient
        gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = test_doc.expected_data
        mock_response.input_tokens = 2000
        mock_response.output_tokens = 100
        mock_response.cost_usd = 0.0001
        gemini_client.call_flash.return_value = mock_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Real Gate Linter (validates actual data)
        gate_linter = GateLinter()

        # Execute extraction
        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Verify success
        assert result.status == "SUCCESS"
        assert result.schema is not None
        assert result.schema.management_id == test_doc.expected_data["management_id"]
        assert result.schema.company_name == test_doc.expected_data["company_name"]
        assert str(result.schema.issue_date) == test_doc.expected_data["issue_date"]
        assert result.final_model == "flash"
        assert len(result.attempts) == 1
        assert result.total_cost > 0

    def test_end_to_end_invoice_success(self) -> None:
        """Test successful end-to-end extraction for invoice."""
        test_doc = TEST_DOCUMENTS[1]  # High confidence invoice

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
            reason=None,
        )

        # Mock GeminiClient
        gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = test_doc.expected_data
        mock_response.input_tokens = 2000
        mock_response.output_tokens = 100
        mock_response.cost_usd = 0.0001
        gemini_client.call_flash.return_value = mock_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Real Gate Linter
        gate_linter = GateLinter()

        # Execute extraction
        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Verify success
        assert result.status == "SUCCESS"
        assert result.schema is not None
        assert result.schema.invoice_number == test_doc.expected_data["invoice_number"]
        assert result.final_model == "flash"

    def test_end_to_end_flash_fail_pro_success(self) -> None:
        """Test Flash fails Gate Linter, Pro succeeds."""
        test_doc = TEST_DOCUMENTS[3]  # Complex invoice

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
            reason=None,
        )

        # Mock GeminiClient - Flash returns incomplete data
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {
            "document_type": "invoice",
            "invoice_number": "",  # Empty - fails Gate Linter
            "company_name": "株式会社複雑商事",
            "issue_date": "2025-01-20",
            "total_amount": 55000,
            "tax_amount": 5000,
        }
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001

        # Pro returns complete data
        pro_response = MagicMock()
        pro_response.data = test_doc.expected_data
        pro_response.input_tokens = 10000
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.001

        gemini_client.call_flash.return_value = flash_response
        gemini_client.call_pro.return_value = pro_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Real Gate Linter
        gate_linter = GateLinter()

        # Execute extraction
        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Verify Pro escalation success
        assert result.status == "SUCCESS"
        assert result.final_model == "pro"
        assert len(result.attempts) == 2
        assert result.attempts[0].model == "flash"
        assert result.attempts[1].model == "pro"
        budget_manager.increment_pro_usage.assert_called_once()

    def test_multiple_documents_success_rate(self) -> None:
        """Test success rate across multiple documents."""
        results = []
        total_cost_usd = 0.0

        for test_doc in TEST_DOCUMENTS:
            gemini_input = GeminiInput(
                markdown=test_doc.markdown,
                include_image=test_doc.confidence < 0.85,
                reason=(
                    f"low_confidence:{test_doc.confidence:.3f}"
                    if test_doc.confidence < 0.85
                    else None
                ),
            )

            # Mock GeminiClient
            gemini_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = test_doc.expected_data
            mock_response.input_tokens = (
                10000 if test_doc.confidence < 0.85 else 2000
            )  # Image adds tokens
            mock_response.output_tokens = 100
            mock_response.cost_usd = (
                0.001 if test_doc.confidence < 0.85 else 0.0001
            )  # Image costs more
            gemini_client.call_flash.return_value = mock_response

            # Mock BudgetManager
            budget_manager = MagicMock()
            budget_manager.check_pro_budget.return_value = True

            # Real Gate Linter
            gate_linter = GateLinter()

            # Execute extraction
            result = extract_with_retry(
                gemini_input=gemini_input,
                schema_class=test_doc.expected_schema_class,
                gemini_client=gemini_client,
                budget_manager=budget_manager,
                gate_linter=gate_linter,
            )

            results.append(result)
            total_cost_usd += result.total_cost

        # Calculate metrics
        successful = sum(1 for r in results if r.status == "SUCCESS")
        success_rate = successful / len(results)
        avg_cost_usd = total_cost_usd / len(results)

        # Convert to JPY (1 USD ≈ ¥145)
        avg_cost_jpy = avg_cost_usd * 145

        # Verify completion criteria
        assert success_rate >= 0.90, f"Success rate {success_rate:.2%} below 90% target"
        assert (
            avg_cost_jpy < 2.0
        ), f"Average cost ¥{avg_cost_jpy:.2f} exceeds ¥2.00 target"

        # Print metrics for visibility
        print(f"\n=== Integration Test Metrics ===")
        print(f"Documents tested: {len(results)}")
        print(f"Success rate: {success_rate:.1%} (target: ≥90%)")
        print(f"Average cost: ¥{avg_cost_jpy:.4f} (target: <¥2.00)")
        print(f"Total cost: ¥{total_cost_usd * 145:.4f}")
        print("=" * 35)

    def test_cost_tracking_accuracy(self) -> None:
        """Test that cost tracking is accurate across attempts."""
        test_doc = TEST_DOCUMENTS[0]

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
        )

        # Mock GeminiClient with known costs
        gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = test_doc.expected_data
        mock_response.input_tokens = 2000
        mock_response.output_tokens = 100
        mock_response.cost_usd = 0.0001  # Flash cost
        gemini_client.call_flash.return_value = mock_response

        budget_manager = MagicMock()
        gate_linter = GateLinter()

        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Verify cost tracking
        assert len(result.attempts) == 1
        assert result.attempts[0].cost_usd == 0.0001
        assert result.total_cost == 0.0001
        assert result.attempts[0].prompt_tokens == 2000
        assert result.attempts[0].output_tokens == 100

    def test_audit_trail_completeness(self) -> None:
        """Test that audit trail captures all attempts."""
        test_doc = TEST_DOCUMENTS[0]

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
        )

        # Mock GeminiClient - First fails, second succeeds
        from core.gemini import SyntaxValidationError

        gemini_client = MagicMock()
        success_response = MagicMock()
        success_response.data = test_doc.expected_data
        success_response.input_tokens = 2000
        success_response.output_tokens = 100
        success_response.cost_usd = 0.0001

        gemini_client.call_flash.side_effect = [
            SyntaxValidationError("Invalid JSON"),
            success_response,
        ]

        budget_manager = MagicMock()
        gate_linter = GateLinter()

        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Verify audit trail
        assert result.status == "SUCCESS"
        assert len(result.attempts) == 2
        assert result.attempts[0].error is not None
        assert "Syntax error" in result.attempts[0].error
        assert result.attempts[1].error is None
        assert result.attempts[1].data == test_doc.expected_data
        assert result.total_cost == sum(a.cost_usd for a in result.attempts)


# ============================================================
# Performance Tests
# ============================================================


class TestPipelinePerformance:
    """Test pipeline performance characteristics."""

    def test_flash_only_performance(self) -> None:
        """Test that Flash-only path is cost-efficient."""
        test_doc = TEST_DOCUMENTS[0]

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
        )

        gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = test_doc.expected_data
        mock_response.input_tokens = 2000
        mock_response.output_tokens = 100
        mock_response.cost_usd = 0.0001
        gemini_client.call_flash.return_value = mock_response

        budget_manager = MagicMock()
        gate_linter = GateLinter()

        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Flash-only should be very cheap
        assert result.total_cost < 0.0005  # < $0.0005 = ¥0.07
        assert result.final_model == "flash"
        gemini_client.call_pro.assert_not_called()

    def test_pro_escalation_cost(self) -> None:
        """Test that Pro escalation increases cost but stays under target."""
        test_doc = TEST_DOCUMENTS[1]

        gemini_input = GeminiInput(
            markdown=test_doc.markdown,
            include_image=False,
        )

        # Mock Flash failure → Pro success
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {
            "invoice_number": "",  # Empty - fails Gate
            "company_name": "Test",
            "issue_date": "2025-01-15",
            "total_amount": 50000,
            "tax_amount": 5000,
        }
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001

        pro_response = MagicMock()
        pro_response.data = test_doc.expected_data
        pro_response.input_tokens = 10000
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.001

        gemini_client.call_flash.return_value = flash_response
        gemini_client.call_pro.return_value = pro_response

        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        gate_linter = GateLinter()

        result = extract_with_retry(
            gemini_input=gemini_input,
            schema_class=test_doc.expected_schema_class,
            gemini_client=gemini_client,
            budget_manager=budget_manager,
            gate_linter=gate_linter,
        )

        # Pro escalation should still be under ¥2
        cost_jpy = result.total_cost * 145
        assert cost_jpy < 2.0  # Under target
        assert result.final_model == "pro"
