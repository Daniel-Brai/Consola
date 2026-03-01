from __future__ import annotations

import inspect
from typing import Any

from sqlalchemy import Select, func, select

from consola.errors import translate_error
from consola.exceptions import ConsolaLookupError
from consola.repr import patch_instance, patch_list
from consola.session import BridgedSession

__all__ = ["ModelProxy"]


class ModelProxy:
    """
    A proxy for a SQLAlchemy or SQLModel model class, providing convenient methods for common CRUD operations
    """

    def __init__(self, model_cls: type, session: BridgedSession, *, auto_tx: bool = True) -> None:
        self._model = model_cls
        self._session = session
        self._auto_tx = auto_tx
        self.__wrapped__ = model_cls
        self.__name__ = model_cls.__name__
        self.__doc__ = model_cls.__doc__

    def _commit_or_not(self) -> None:
        """
        Commit only when in auto-tx mode and no explicit block is open
        """

        if self._auto_tx:
            self._session.commit()

    def _run_write(self, fn: Any, params: dict[str, Any] | None = None) -> Any:
        try:
            result = fn()
            self._commit_or_not()
            return result
        except Exception as exc:
            self._session.rollback()
            consola_exc = translate_error(exc, params=params or {})
            raise consola_exc from exc

    def find(self, pk: Any) -> Any:
        """
        Return the record with this primary key, or None

        Args:
            pk (Any): The primary key value to search for.

        Returns:
            Any: The record with the specified primary key, or None if not found.
        """

        obj = self._session.get(self._model, pk)
        return patch_instance(obj) if obj is not None else None

    def find_or_raise(self, pk: Any) -> Any:
        """
        Return the record with this primary key, or raise LookupError if not found.

        Args:
            pk (Any): The primary key value to search for.

        Returns:
            Any: The record with the specified primary key.

        Raises:
            ConsolaLookupError: If no record with the specified primary key is found
        """

        obj = self._session.get(self._model, pk)
        if obj is None:
            raise ConsolaLookupError(f"{self._model.__name__} pk={pk!r} not found")

        return patch_instance(obj)

    def where(self, **kwargs: Any) -> list[Any]:
        """
        Retrieve records matching the specified keyword arguments as equality filters

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by.

        Returns:
            list[Any]: A list of records matching the specified filters.
        """

        stmt: Select[tuple[Any]] = select(self._model).filter_by(**kwargs)
        return patch_list(list(self._session.scalars(stmt).all()))

    def find_by(self, **kwargs: Any) -> Any:
        """
        Retrieve the first record matching kwargs, or None

        Use instead of `where()` when you need a single instance

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by

        Returns:
            Any: The first record matching the specified filters, or None if not found
        """

        stmt: Select[tuple[Any]] = select(self._model).filter_by(**kwargs).limit(1)
        return patch_instance(self._session.scalars(stmt).first())

    def all(self) -> list[Any]:
        """
        Retrieve all records of this model

        Returns:
            list[Any]: A list of all records of this model
        """

        return patch_list(list(self._session.scalars(select(self._model)).all()))

    def first(self) -> Any:
        """
        Retrieve the first record based on primary key ordering, or None if no records exist

        Returns:
            Any: The first record based on primary key ordering, or None if no records exist
        """
        return patch_instance(self._session.scalars(select(self._model).limit(1)).first())

    def first_by(self, cols: list[str]) -> Any:
        """
        Retrieve the first record based on some others columns ordering, or None if no records match

        Args:
            cols (list[str]): A list of column names to order by in ascending order

        Returns:
            Any: The first record matching the specified ordering, or None if no records match
        """

        stmt: Select[tuple[Any]] = select(self._model)

        for col in cols:
            col_attr = getattr(self._model, col, None)
            if col_attr is not None:
                stmt = stmt.order_by(col_attr.asc())

        stmt = stmt.limit(1)
        return patch_instance(self._session.scalars(stmt).first())

    def last(self) -> Any:
        """
        Retrieve the last record based on primary key ordering, or None if no records exist

        Returns:
            Any: The last record based on primary key ordering, or None if no records exist
        """

        from sqlalchemy import inspect as sa_inspect

        pk_cols: list[Any] = list(sa_inspect(self._model).mapper.primary_key)
        stmt: Select[tuple[Any]] = select(self._model).order_by(*[c.desc() for c in pk_cols]).limit(1)
        return patch_instance(self._session.scalars(stmt).first())

    def last_by(self, cols: list[str]) -> Any:
        """
        Retrieve the last record based on some others columns ordering, or None if no records match

        Args:
            cols (list[str]): A list of column names to order by in descending order

        Returns:
            Any: The last record matching the specified ordering, or None if no records match
        """

        stmt: Select[tuple[Any]] = select(self._model)

        for col in cols:
            col_attr = getattr(self._model, col, None)
            if col_attr is not None:
                stmt = stmt.order_by(col_attr.desc())

        stmt = stmt.limit(1)
        return patch_instance(self._session.scalars(stmt).first())

    def count(self, **kwargs: Any) -> int:
        """
        Retrieve the count of records matching the specified keyword arguments as equality filters

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by.

        Returns:
            int: The count of records matching the specified filters.
        """

        stmt: Select[tuple[int]] = select(func.count()).select_from(self._model)
        if kwargs:
            stmt = stmt.filter_by(**kwargs)

        return self._session.scalar(stmt) or 0

    def exists(self, **kwargs: Any) -> bool:
        """
        Check if any record exists matching the specified keyword arguments as equality filters

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by.

        Returns:
            bool: True if at least one record exists matching the specified filters, False otherwise.
        """

        return self.count(**kwargs) > 0

    def create(self, **kwargs: Any) -> Any:
        """
        Create and persist a new record

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to set on the new record

        Returns:
            Any: The newly created and persisted record
        """

        def _do():
            obj = self._model(**kwargs)
            self._session.add(obj)
            self._session.flush()
            self._session.refresh(obj)
            return patch_instance(obj)

        return self._run_write(_do, params=kwargs)

    def create_all(self, records: list[dict[str, Any]]) -> list[Any]:
        """
        Create and persist multiple records in a batch

        Args:
            records (list[dict[str, Any]]): A list of dictionaries, each representing column-value pairs to set on a new record

        Returns:
            list[Any]: A list of the newly created and persisted records
        """

        def _do():
            objs = [self._model(**kwargs) for kwargs in records]
            for obj in objs:
                self._session.add(obj)

            self._session.flush()

            for obj in objs:
                self._session.refresh(obj)

            return patch_list(objs)

        return self._run_write(_do, params={"records": records})

    def update(self, pk: Any, **values: Any) -> Any:
        """
        Update a single record by primary key

        Args:
            pk (Any): The primary key value of the record to update
            **values: Arbitrary keyword arguments representing column-value pairs to update on the record

        Returns:
            Any: The updated record

        Raises:
            ConsolaLookupError: If no record with the specified primary key is found
        """

        def _do():
            obj = self._session.get(self._model, pk)
            if obj is None:
                raise ConsolaLookupError(f"{self._model.__name__} pk={pk!r} not found")

            for k, v in values.items():
                setattr(obj, k, v)

            self._session.flush()
            self._session.refresh(obj)

            return patch_instance(obj)

        return self._run_write(_do, params={"pk": pk, **values})

    def update_by(self, where: dict[str, Any] | None = None, **values: Any) -> Any:
        """
        Update a single record matching the where filters, or the first record if where is None

        Args:
            where (dict[str, Any] | None): A dictionary of column-value pairs to filter by. If None, updates the first record.
            **values: Arbitrary keyword arguments representing column-value pairs to update on the record

        Returns:
            Any: The updated record

        Raises:
            ConsolaLookupError: If no record matching the specified filters is found
        """

        def _do():
            stmt: Select = select(self._model)
            if where:
                stmt = stmt.filter_by(**where)

            obj = self._session.scalars(stmt).first()
            if obj is None:
                raise ConsolaLookupError(f"{self._model.__name__} matching {where!r} not found")

            for k, v in values.items():
                setattr(obj, k, v)

            self._session.flush()
            self._session.refresh(obj)

            return patch_instance(obj)

        return self._run_write(_do, params={"where": where, **values})

    def update_all(self, where: dict[str, Any] | None = None, **values: Any) -> list[Any]:
        """
        Update all records matching the where filters, or all records if where is None

        Args:
            where (dict[str, Any] | None): A dictionary of column-value pairs to filter by. If None, updates all records.
            **values: Arbitrary keyword arguments representing column-value pairs to update on the records

        Returns:
            list[Any]: A list of the updated records
        """

        def _do():
            stmt: Select = select(self._model)
            if where:
                stmt = stmt.filter_by(**where)

            objs = list(self._session.scalars(stmt).all())
            for obj in objs:
                for k, v in values.items():
                    setattr(obj, k, v)

            self._session.flush()

            for obj in objs:
                self._session.refresh(obj)

            return patch_list(objs)

        return self._run_write(_do, params={"where": where, **values})

    def destroy(self, pk: Any) -> Any:
        """
        Delete the record with this primary key

        Args:
            pk (Any): The primary key value of the record to delete

        Returns:
            Any: The deleted record (detached)
        """

        def _do():
            obj = self._session.get(self._model, pk)

            if obj is None:
                raise LookupError(f"{self._model.__name__} pk={pk!r} not found")

            self._session.delete(obj)
            self._session.flush()

            return patch_instance(obj)

        return self._run_write(_do, params={"pk": pk})

    def destroy_by(self, **kwargs: Any) -> Any:
        """
        Delete the first record matching kwargs

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by

        Returns:
            Any: The deleted record (detached)
        """

        def _do():
            stmt: Select[tuple[Any]] = select(self._model).filter_by(**kwargs).limit(1)
            obj = self._session.scalars(stmt).first()

            if obj is None:
                raise LookupError(f"{self._model.__name__} matching {kwargs!r} not found")

            self._session.delete(obj)
            self._session.flush()

            return patch_instance(obj)

        return self._run_write(_do, params=kwargs)

    def destroy_all(self, **kwargs: Any) -> list[Any]:
        """
        Delete all rows matching kwargs

        Args:
            **kwargs: Arbitrary keyword arguments representing column-value pairs to filter by

        Returns:
            list[Any]: A list of the deleted instances (detached)
        """

        def _do():
            stmt: Select[tuple[Any]] = select(self._model)
            if kwargs:
                stmt = stmt.filter_by(**kwargs)

            objs = list(self._session.scalars(stmt).all())

            for obj in objs:
                self._session.delete(obj)
            self._session.flush()

            return patch_list(objs)

        return self._run_write(_do, params=kwargs)

    @property
    def columns(self) -> None:
        """
        Print a rich table of column metadata: name, type, PK, FK, nullable, unique, default
        """
        from rich.console import Console as RichConsole
        from rich.table import Table
        from sqlalchemy import inspect as sa_inspect

        _c = RichConsole()
        sa_mapper: Any = sa_inspect(self._model)

        t = Table(
            show_header=True,
            header_style="bold magenta",
            box=None,
            padding=(0, 2),
        )
        t.add_column("Column", style="cyan")
        t.add_column("Type", style="dim")
        t.add_column("PK", justify="center")
        t.add_column("FK", justify="center", style="dim cyan")
        t.add_column("Nullable", justify="center")
        t.add_column("Unique", justify="center")
        t.add_column("Default", style="dim")

        for col in sa_mapper.mapper.columns:
            pk = "[bold green]✓[/bold green]" if col.primary_key else ""
            fk_targets = ", ".join(str(f.target_fullname) for f in col.foreign_keys)
            fk = fk_targets if fk_targets else ""
            nullable = "" if col.nullable else "[dim]✗[/dim]"
            unique = "[bold]✓[/bold]" if col.unique else ""
            default = ""
            if col.default is not None and hasattr(col.default, "arg"):
                default = str(col.default.arg)
            elif col.server_default is not None and hasattr(col.server_default, "arg"):
                default = f"server:{str(col.server_default.arg)[:20]}"
            t.add_row(col.key, str(col.type), pk, fk, nullable, unique, default)

        _c.print(f"\n[bold cyan]{self._model.__name__}[/bold cyan] [dim]→ {self.table_name}[/dim]")
        _c.print(t)
        _c.print()

    @property
    def table_name(self) -> str:
        """
        Get the table name for this model, if available.

        This is typically defined by the `__tablename__` attribute on SQLAlchemy models.

        This is a best-effort attempt that tries multiple strategies to determine the table name,
        and falls back to the model class name in lowercase if all else fails.
        """

        from sqlalchemy import inspect as sa_inspect

        sa_mapper: Any = sa_inspect(self._model)
        return (
            sa_mapper.local_table.name  # type: ignore[attr-defined]
            or self._model.__tablename__  # type: ignore[attr-defined]
            or self._model.__table__.name  # type: ignore[attr-defined]
            or self._model.__name__.lower()
        )

    def __repr__(self) -> str:
        return f"<ModelProxy {self._model.__name__}>"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._model(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._model, name, None)

        if attr is None:
            raise ConsolaLookupError(f"{self._model.__name__} has no attribute {name!r}")

        if callable(attr):
            if inspect.iscoroutinefunction(attr):

                async def async_method(*args: Any, **kwargs: Any) -> Any:
                    return await attr(*args, **kwargs)

                return async_method
            else:

                def method(*args: Any, **kwargs: Any) -> Any:
                    return attr(*args, **kwargs)

            return method
        else:
            return attr
