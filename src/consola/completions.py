"""
Tab-completion for the Consola REPL

This module configures readline to provide tab-completion for:
    - model names from the discovered registry
    - helper methods when user types ``ModelName.``
    - everything in the local namespace
"""

from __future__ import annotations

import readline
import rlcompleter
from typing import Any

__all__ = ["setup_completions"]

_HELPER_METHODS = [
    "find(",
    "find_or_raise(",
    "find_by(",
    "where(",
    "all()",
    "first()",
    "first_by(",
    "last()",
    "last_by(",
    "count(",
    "exists(",
    "create(",
    "create_all(",
    "update(",
    "update_by(",
    "update_all(",
    "destroy(",
    "destroy_by(",
    "destroy_all(",
    "columns()",
    "table_name()",
]


def setup_completions(namespace: dict[Any, Any], model_names: list[str]) -> None:
    """
    Configure readline to provide tab-completion for the Consola REPL

    Args:
        namespace (dict[Any, Any]): The local namespace to use for tab-completion.
        model_names (list[str]): The list of model names to include in tab-completion.

    Returns:
        None
    """

    py_completer = rlcompleter.Completer(namespace)

    def completer(text: str, state: int) -> str | None:
        if "." in text:
            prefix, attr = text.rsplit(".", 1)
            candidates: list[str] = [f"{prefix}.{m}" for m in _HELPER_METHODS if m.startswith(attr)]
            i = 0
            while True:
                c = py_completer.complete(text, i)
                if c is None:
                    break
                candidates.append(c)
                i += 1
            try:
                return candidates[state]
            except IndexError:
                return None
        else:
            candidates = [n for n in model_names if n.startswith(text)]
            i = 0
            while True:
                c = py_completer.complete(text, i)
                if c is None:
                    break
                candidates.append(c)
                i += 1

            seen: set[str] = set()
            unique: list[str] = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    unique.append(c)

            try:
                return unique[state]
            except IndexError:
                return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" \t\n`!@#$^&*()=+[{]}|;:'\",<>?")
