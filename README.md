# Polyansky Bot

![Python](https://img.shields.io/badge/python-3.14-blue.svg) ![Ruff](https://img.shields.io/badge/style-ruff-%23cc66cc.svg?logo=ruff&logoColor=white) ![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen.svg)

Telegram Bot for Vyatskie Polyany

---

## Table of Contents

- [Polyansky Bot](#polyansky-bot)
  - [Table of Contents](#table-of-contents)
  - [Requirements](#requirements)
  - [Before You Start](#before-you-start)
    - [Required](#required)
    - [Optional](#optional)

---

## Requirements

- Tested on **Fedora 42**
- Requires **Python 3.13**
- All dependencies are listed in [`pyproject.toml`](./pyproject.toml)

---

## Before You Start

### Required

To install all dependencies use [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

To get rid of workarounds with path imports:

```bash
uv pip install -e .
```

### Optional

Optionally, enable pre-commit hooks for auto-formatting/linting:

```bash
uv run pre-commit install
```

To test that hook has successfully installed:

```bash
uv run pre-commit run --all-files
```
