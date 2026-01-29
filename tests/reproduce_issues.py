from datetime import date

from pydantic import ValidationError
from src.core.linters.gate import GateLinter
from src.core.schemas import DeliveryNoteV2, OrderFormV1


def test_delivery_note_none_date():
    print("Testing DeliveryNoteV2 with delivery_date=None...")
    data = {
        "management_id": "123",
        "company_name": "Test Co",
        "issue_date": date(2025, 1, 1),
        "delivery_date": None,  # EXPLICIT NONE
        "total_amount": 1000,
    }
    try:
        model = DeliveryNoteV2(**data)
        print("Success!")
        print(model.model_dump())
    except ValidationError as e:
        print("Validation Failed!")
        print(e)
    except Exception as e:
        print(f"Unexpected error: {e}")


def test_order_form_gate_linter():
    print("\nTesting OrderFormV1 with document_type='OrderForm'...")
    data = {
        "document_type": "OrderForm",  # PascalCase
        "order_number": "123",
        # other optional fields...
    }
    # Create model first (Pydantic check)
    try:
        _ = OrderFormV1(**data)
        print("Pydantic Validation Passed.")
    except Exception as e:
        print(f"Pydantic Validation Failed: {e}")
        return

    # Now check Gate Linter
    linter = GateLinter()
    # Simulate fix: Enforce document_type from schema default
    if hasattr(OrderFormV1, "model_fields") and "document_type" in OrderFormV1.model_fields:
        field = OrderFormV1.model_fields["document_type"]
        if field.default is not None:
            data["document_type"] = field.default
            print(f"Applied fix: document_type -> {data['document_type']}")

    # GateLinter validates dict/json
    result = linter.validate(data)
    if result.passed:
        print("Gate Linter Passed.")
    else:
        print("Gate Linter Failed:")
        print(result.errors)


if __name__ == "__main__":
    test_delivery_note_none_date()
    test_order_form_gate_linter()
