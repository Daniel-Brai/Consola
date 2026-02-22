"""
Consola CLI - Interactive SQL console for SQLAlchemy or  SQLModel projects

    consola start                                  auto-discover engine
    consola start --db myapp.database:engine       explicit module and variable name
    consola start --no-transaction
    consola start --no-sql-log
    consola start --no-ipython
    consola start --audit-db <url>
    consola start --scan <dir>

    consola audit list
    consola audit list --pending
    consola audit review <id>
    consola audit stats
"""

from importlib.metadata import version

from consola.constants import PACKAGE_NAME

__version__ = version(PACKAGE_NAME)


def main() -> None:
    from consola.cli import app

    app()


__all__ = ["main"]
