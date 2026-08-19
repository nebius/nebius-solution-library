"""Single fail-closed refusal type for the node-local OCI switch adapter.

Every guard in this package raises ``Refusal`` with a stable machine-readable
``code``.  Nothing in this package returns a falsy value to signal denial and
nothing swallows an exception: a check either passes silently or raises.
"""

from __future__ import annotations


class Refusal(Exception):
    """A fail-closed denial. ``code`` is stable; ``detail`` is for humans."""

    def __init__(self, code: str, detail: str) -> None:
        if not code or not code.replace("-", "").replace(".", "").isalnum():
            raise ValueError(f"refusal code must be kebab/dotted alnum: {code!r}")
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def require(condition: bool, code: str, detail: str) -> None:
    """Raise ``Refusal(code, detail)`` unless ``condition`` is exactly True."""
    if condition is not True:
        raise Refusal(code, detail)
