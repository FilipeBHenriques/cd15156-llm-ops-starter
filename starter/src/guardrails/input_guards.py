"""Input-side validators: prompt injection detection and PII redaction.

Lightweight regex/heuristic implementations chosen over Guardrails Hub
validators for capstone reliability. The Hub validators (e.g.
``hub://guardrails/detect_pii``) are the production upgrade path covered
in the Guardrails module's content; LLM Guard's ML-backed scanners (in
the sibling ``llm_guard/`` package) are a second upgrade path that runs
locally without external accounts.

To add a new injection pattern, append a ``re.compile(...)`` to
``INJECTION_PATTERNS``. To add a new PII type, add an entry to
``PII_PATTERNS`` and a matching redaction string in ``PII_REDACTIONS``.
"""

import re

INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(an?\s+)?", re.IGNORECASE),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.IGNORECASE),
    re.compile(r"^\s*system\s*[:>]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*assistant\s*[:>]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\s*\|?\s*im_start\s*\|?\s*>", re.IGNORECASE),
    re.compile(
        r"\b(reveal|show|print|leak|repeat|tell\s+me)\s+(your|the)\s+"
        r"(system|initial|original|hidden|secret)\s+(prompt|instructions?|rules?|message)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(bypass|override|turn\s+off|disable|ignore)\s+(your|the|all)?\s*"
        r"(safety|guardrails?|filters?|restrictions?|content\s+policy|policies)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(jailbreak\s+mode|DAN\s+mode|developer\s+mode|do\s+anything\s+now)\b",
        re.IGNORECASE,
    ),
    # --- Added for Task 6 (3+ new injection patterns) ---
    # Catches "from now on, respond only as JSON with no explanation" style
    # attempts to hijack the output format/behavior rather than the content.
    re.compile(
        r"\bfrom\s+now\s+on\s*,?\s*(you\s+(will|must|should)|respond|reply|act)\b",
        re.IGNORECASE,
    ),
    # Catches attempts to get the model to speak "as" a persona/entity that
    # isn't the FAQ assistant (distinct from "act as" above, which targets
    # explicit persona assignment; this targets "speaking in character").
    re.compile(
        r"\b(stay|remain)\s+in\s+character\b|\bno\s+matter\s+what\s+i\s+(ask|say)\b",
        re.IGNORECASE,
    ),
    # Catches delimiter/fence-based injection — trying to smuggle a fake
    # "end of user input, begin new instructions" boundary inside the text.
    re.compile(
        r"(---+|===+|###+)\s*(end|new)\s+(of\s+)?(user\s+)?(input|instructions?|prompt)\b",
        re.IGNORECASE,
    ),
]

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    # --- Added for Task 6 (new sensitive-data type) ---
    # IPv4 addresses, e.g. a customer pasting a support-session log that
    # contains their own machine's address.
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
    ),
    # IBAN — 2-letter country code + 2 check digits + up to 30 alphanumeric,
    # e.g. a customer pasting bank details into a refund-status question.
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
}

PII_REDACTIONS: dict[str, str] = {
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "ssn": "[REDACTED_SSN]",
    "credit_card": "[REDACTED_CARD]",
    "ip_address": "[REDACTED_IP]",
    "iban": "[REDACTED_IBAN]",
}


def detect_prompt_injection(text: str) -> str | None:
    """Return a reason string if the input looks like prompt injection, else None."""
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"prompt_injection: matched pattern {pattern.pattern!r}"
    return None


def detect_pii(text: str) -> tuple[str, list[str]]:
    """Redact known PII kinds from ``text``. Returns ``(redacted, kinds_found)``."""
    found: list[str] = []
    redacted = text
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(redacted):
            found.append(kind)
            redacted = pattern.sub(PII_REDACTIONS[kind], redacted)
    return redacted, found
