"""
Rich repr for model instances returned from the Consola REPL

It patches __repr__ so that every model instance returned by a ModelProxy in the REPL prints:

    #<User id=1 name="Daniel" active=True>
    #<Currency id=3 code="NGN" name="Nigerian Naira">
"""

from __future__ import annotations

from typing import Any

from consola.types import ConsolaList

__all__ = ["patch_instance", "patch_list"]


_patched_classes: dict[type, type] = {}


def _col_values(obj: Any) -> dict[str, Any]:
    try:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(obj)

        return {col.key: getattr(obj, col.key, "…") for col in state.mapper.columns}
    except Exception:
        return {}


def _make_repr(obj: Any) -> str:
    cls_name = type(obj).__name__
    pairs = " ".join(f"{k}={v!r}" for k, v in _col_values(obj).items())
    return f"#<{cls_name} {pairs}>"


def patch_instance(obj: Any) -> Any:
    """
    Attach a custom __repr__ to a model instance

    Args:
        obj (Any): A SQLAlchemy mapped model instance

    Returns:
        Any: The same model instance with a patched __repr__
    """

    if obj is None:
        return obj

    try:
        if not getattr(obj, "_consola_repr_patched", False):
            obj.__class__ = _patched_class(type(obj))
            object.__setattr__(obj, "_consola_repr_patched", True)
    except Exception:
        return

    return obj


def patch_list(objs: list[Any]) -> ConsolaList:
    """
    Patch a list of model instances with the custom __repr__

    Args:
        objs (list[Any]): A list of SQLAlchemy mapped model instances

    Returns:
        ConsolaList: A list of the same model instances with patched __repr__ for each instance
    """

    for obj in objs:
        patch_instance(obj)

    return ConsolaList(objs)


def _patched_class(cls: type) -> type:
    if cls in _patched_classes:
        return _patched_classes[cls]

    new_cls = type(
        cls.__name__,
        (cls,),
        {
            "__repr__": lambda self: _make_repr(self),
            "__module__": cls.__module__,
            "__abstract__": True,
        },
    )

    _patched_classes[cls] = new_cls

    return new_cls
