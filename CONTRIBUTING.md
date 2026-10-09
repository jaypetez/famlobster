# Contributing to FamLobster

Thanks for your interest! Bug reports, fixes, docs and features are all welcome.

## Development setup

```bash
git clone https://github.com/jaypetez/famlobster.git && cd famlobster
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install   # optional: runs ruff on commit
```

Copy `.env.example` to `.env` only if you want to run the bot itself. **The test suite needs no credentials**: it uses mocks and never calls live APIs.

## Before opening a PR

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov
```

CI runs the same checks (plus a package build and dependency audit) on Python 3.11, 3.12 and 3.13.

## Pull request workflow

1. Fork the repo and create a branch from `main`.
2. Keep the change focused; add or update tests for behavior changes.
3. Use [Conventional Commit](https://www.conventionalcommits.org/) style titles, e.g. `feat: add recipe ingredient extraction` or `fix: handle all-day events`.
4. Open a PR against `main` and fill in the template.
5. `main` is protected: PRs need passing CI and one approving review from a maintainer. PRs are squash-merged.

## Guidelines

- Never commit secrets (`.env`, `token.json`, `credentials.json`). See [SECURITY.md](SECURITY.md) to report vulnerabilities privately.
- Reminder persistence tests must use the `tmp_reminders_file` fixture.
- See [CLAUDE.md](CLAUDE.md) for an architecture overview.

By contributing you agree your work is licensed under the [MIT License](LICENSE) and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
