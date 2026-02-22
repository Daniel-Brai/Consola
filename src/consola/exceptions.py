from typing import Any


class ConsolaError(Exception):
    """
    Base exception for all Consola errors
    """

    ...


class ConsolaLookupError(ConsolaError, LookupError):
    """
    Raised when a requested record is not found in the database
    """

    ...


class ConsolaTransactionError(ConsolaError):
    """
    Raised when a transaction fails due to issues such as deadlocks, timeouts, or other database errors
    """

    ...


class ConsolaParamsError(ConsolaError):
    """
    Raised when a query fails due to invalid parameters (e.g invalid column name, invalid value type) on the model query
    """

    def __init__(self, message: str, params: dict[str, Any]):
        self.params = params
        super().__init__(message)
