# Consola

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tiny interactive SQL console for exploring SQLAlchemy/SQLModel models and executing ad-hoc SQL against your project's database.

- **Quick start**: Install consola and run the CLI to open an interactive REPL for your project with `consola start`.
- **Async and Sync Engines**: It supports both sync and async SQLAlchemy engines and bridges async sessions with a sync-style API.

## Motivation for Consola

I was inspired by the Rails Console in [Ruby on Rails](https://rubyonrails.org/), a powerful interactive REPL that makes exploring models and querying the database effortless during development. I wanted the same convenience when
working in Python projects that use SQLAlchemy/SQLModel. Consola brings that experience to Python by providing a lightweight, opinionated interactive console for inspecting models using Rails-like methods and running ad-hoc SQL using the model classes.

## License

See [LICENSE](LICENSE) for details.
