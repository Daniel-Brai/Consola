"""
Allows Consola to be run as a module

    python -m consola
    uv run python -m consola
    uv run python -m consola start --db myapp.database:engine
    uv run python -m consola audit list
"""

from consola.cli import app

if __name__ == "__main__":
    app()
