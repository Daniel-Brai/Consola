from typing import TypeAlias

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["AnyEngine", "ConsolaList"]


AnyEngine: TypeAlias = Engine | AsyncEngine


class ConsolaList(list):
    """
    A list subclass whose repr prints one item per line somewhat like Rails

    Example:

        [
            #<User id=1 name="Daniel">,
            #<User id=2 name="Ope">
            #<User id=3 name="Promise">
        ]
    """

    def __repr__(self) -> str:
        if not self:
            return "[]"

        inner = ",\n  ".join(repr(item) for item in self)

        return f"[\n  {inner}\n]"
