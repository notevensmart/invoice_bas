from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.engine.schemas import AccountCodeSuggestion, InvoiceExtraction


DEFAULT_RULE_PATH = Path("config/account_mapping_rules.json")


class AccountCodeMapper:
    def __init__(self, rules_path: str | Path = DEFAULT_RULE_PATH):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def suggest(self, extraction: InvoiceExtraction | None) -> AccountCodeSuggestion:
        if extraction is None:
            return self._unmapped("No invoice extraction was available for account mapping.")

        supplier = (extraction.supplier_name or "").lower()
        descriptions = " ".join(
            item.description or "" for item in extraction.line_items
        ).lower()

        for rule in self.rules:
            match = rule.get("match", {})
            supplier_terms = [term.lower() for term in match.get("supplier_contains", [])]
            description_terms = [
                term.lower() for term in match.get("description_contains", [])
            ]

            supplier_hit = next((term for term in supplier_terms if term in supplier), None)
            description_hit = next(
                (term for term in description_terms if term in descriptions), None
            )
            if supplier_hit or description_hit:
                reason = rule.get("reason") or "Matched local account mapping rule."
                if supplier_hit:
                    reason = f"Matched supplier pattern: {supplier_hit}. {reason}"
                elif description_hit:
                    reason = f"Matched description pattern: {description_hit}. {reason}"
                return AccountCodeSuggestion(
                    suggested_account_code=rule.get("suggested_account_code"),
                    suggested_account_name=rule.get("suggested_account_name"),
                    confidence=rule.get("confidence", "medium"),
                    reason=reason,
                    status="suggested",
                )

        return self._unmapped("No supplier or line-item keyword matched local mapping rules.")

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self.rules_path.exists():
            return []
        return json.loads(self.rules_path.read_text(encoding="utf-8"))

    def _unmapped(self, reason: str) -> AccountCodeSuggestion:
        return AccountCodeSuggestion(
            suggested_account_code="UNMAPPED",
            suggested_account_name="Needs mapping review",
            confidence="low",
            reason=reason,
            status="needs_mapping_review",
        )
