from importlib.metadata import version

from consola.constants import PACKAGE_NAME

__version__ = version(PACKAGE_NAME)


def main() -> None:
    from consola.cli import app

    app()


__all__ = ["main"]
