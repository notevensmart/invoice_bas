from __future__ import annotations


def test_responder_mentions_engine_status_and_issues_without_overriding(processor, text_loader):
    result = processor.process_text("invalid_abn.pdf", text_loader("invalid_abn"))
    response = result.response

    assert response is not None
    assert "Status: needs_review." in response
    assert "INVALID_ABN" in response
    assert "12 345 678 901" in response
    assert "$330.00" in response
    assert "Status: ready." not in response


def test_responder_does_not_invent_missing_buyer_identity(processor, text_loader):
    result = processor.process_text(
        "over_1000_missing_buyer.pdf",
        text_loader("over_1000_missing_buyer"),
    )
    response = result.response or ""

    assert "MISSING_BUYER_FOR_OVER_1000" in response
    assert "Luna Cafe Pty Ltd" not in response
    assert result.status.value == "needs_review"
