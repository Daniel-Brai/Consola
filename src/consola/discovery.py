"""
Discovery utilities for Consola

This module finds every mapped SQLAlchemy or SQLModel class and every Engine or AsyncEngine in the project codebase.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, DeclarativeMeta

from consola.types import AnyEngine

__all__ = ["discover_models", "discover_engines", "ModelRegistry"]


class ModelRegistry:
    """
    Registry for discovered model classes
    """

    def __init__(self) -> None:
        self._models: dict[str, type] = {}

    def register(self, cls: type) -> None:
        self._models[cls.__name__] = cls

    def all(self) -> dict[str, type]:
        return dict(self._models)

    def names(self) -> list[str]:
        return list(self._models)

    def clear(self) -> None:
        self._models.clear()

    def __len__(self) -> int:
        return len(self._models)

    def __repr__(self) -> str:
        return f"<ModelRegistry [{', '.join(self._models)}]>"


def _is_mapped(cls: type) -> bool:
    try:
        from sqlalchemy import inspect as sa_inspect

        insp: Any = sa_inspect(cls, raiseerr=False)
        return insp is not None and hasattr(insp, "mapper")
    except Exception:
        return False


def _walk_subclasses(base: type, registry: ModelRegistry) -> None:
    for cls in base.__subclasses__():
        mod = getattr(cls, "__module__", "")
        if isinstance(mod, str) and mod.startswith("consola."):
            continue

        if _is_mapped(cls):
            registry.register(cls)

        _walk_subclasses(cls, registry)


def _load_module(path: Path) -> ModuleType | None:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if not spec or not spec.loader:
        return None

    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        sys.modules.setdefault(path.stem, mod)
        return mod
    except Exception:
        return None


def _scan_modules(search_paths: list[str] | list[Path]) -> list[ModuleType]:
    mods: list[ModuleType] = []
    for raw in search_paths:
        for py in Path(raw).rglob("*.py"):
            m = _load_module(py)
            if m:
                mods.append(m)
    return mods


def discover_engines(
    search_paths: list[str] | list[Path] | None = None,
    extra_modules: list[ModuleType] | None = None,
) -> list[AnyEngine]:
    """
    Discover all Engine or AsyncEngine instances in the project codebase

    Args:
        search_paths (Optional[list[str | Path]]): Optional list of directories to scan for .py files to load as modules.
        extra_modules (Optional[List[ModuleType]]): Optional list of already-loaded modules to include in the search.

    Returns:
        list[AnyEngine]: List of discovered Engine and AsyncEngine instances.
    """

    pool: list[ModuleType] = list(extra_modules or [])
    if search_paths:
        pool.extend(_scan_modules(search_paths))

    pool.extend(m for m in sys.modules.values() if isinstance(m, ModuleType))

    found: list[AnyEngine] = []
    seen_ids: set[int] = set()

    for mod in pool:
        try:
            members = list(vars(mod).values())
        except Exception as exc:  # re-raise interrupts, otherwise skip module
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            continue

        for obj in members:
            if id(obj) in seen_ids:
                continue

            if isinstance(obj, (Engine, AsyncEngine)):
                seen_ids.add(id(obj))
                found.append(obj)

    return found


def discover_models(
    search_paths: list[str] | list[Path] | None = None,
    extra_modules: list[ModuleType] | None = None,
    bases: list[type] | None = None,
    registry: ModelRegistry | None = None,
) -> ModelRegistry:
    """
    Discover all mapped SQLAlchemy or SQLModel classes in the project codebase

    Args:
            search_paths (Optional[list[str] | list[Path]]): Optional list of directories to scan for .py files to load as modules.
            extra_modules (Optional[List[ModuleType]]): Optional list of already-loaded modules to include in the search.
            bases (Optional[List[type]]): Optional list of base classes to start the search from (e.g., DeclarativeBase subclasses).
            registry (Optional[ModelRegistry]): Optional ModelRegistry instance to populate. If not provided, a new one is created.

    Returns:
            ModelRegistry: A registry containing all discovered model classes.
    """

    reg = registry or ModelRegistry()
    reg.clear()

    for base in bases or []:
        _walk_subclasses(base, reg)

    pool: list[ModuleType] = list(extra_modules or [])
    if search_paths:
        pool.extend(_scan_modules(search_paths))

    pool.extend(m for m in sys.modules.values() if isinstance(m, ModuleType))

    seen: set[int] = set()
    for mod in pool:
        try:
            members = inspect.getmembers(mod, inspect.isclass)
        except Exception as exc:  # re-raise interrupts, otherwise skip module
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            continue

        for _, cls in members:
            if id(cls) in seen:
                continue

            seen.add(id(cls))

            consola_mod: Any = getattr(cls, "__module__", "")
            if isinstance(consola_mod, str) and consola_mod.startswith("consola."):
                continue

            if isinstance(type(cls), DeclarativeMeta) and _is_mapped(cls):
                reg.register(cls)
                continue

            try:
                if issubclass(cls, DeclarativeBase) and cls is not DeclarativeBase and not _is_mapped(cls):
                    _walk_subclasses(cls, reg)
                    continue
            except TypeError:
                pass

            try:
                import sqlmodel  # noqa: PLC0415

                if (
                    issubclass(cls, sqlmodel.SQLModel)
                    and cls is not sqlmodel.SQLModel
                    and getattr(cls, "__tablename__", None)
                    and _is_mapped(cls)
                ):
                    reg.register(cls)
            except ImportError:
                pass

    return reg
