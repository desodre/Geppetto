# Geppetto — Android UI Automation Framework

Geppetto is a high-level Python framework for Android automation, designed with a focus on ergonomics and composition. It orchestrates ADB, Fastboot, and UIAutomator2 to provide a unified API for controlling devices.

## Project Overview

- **Architecture**: Composition-based. The `Device` class (in `src/geppetto/device.py`) acts as the primary facade, delegating to specialized services (`core/`, `services/`, `ui/`).
- **Tech Stack**: Python 3.12+, `uv` (dependency management), `hatchling` (build backend), `lxml` (XML parsing), `uiautomator2` (UI interactions).
- **Core Components**:
    - `core/`: Transport layers for ADB and Fastboot.
    - `ui/`: Models for UI elements (Widgets, Bounds, Windows).
    - `services/`: Specialized controllers for WiFi, Lockscreen, and Notifications.
    - `analyzers/`: Optional image/video analysis tools (OpenCV, ImageHash).

## Building and Running

This project uses `uv` for modern dependency management.

### Environment Setup

```bash
# Sync dependencies and create .venv
uv sync --all-extras
```

### Development Commands

- **Linting**: `uv run ruff check src`
- **Formatting**: `uv run ruff format src`
- **Type Checking**: `uv run mypy src`
- **Testing**: `uv run pytest` (Ensure tests are located in `tests/` or equivalent)

## Development Conventions

- **Python Version**: Strict requirement of **Python 3.12+**.
- **Coding Style**:
    - Follow **PEP 8** conventions.
    - Use **snake_case** for variables, functions, and attributes (e.g., `content_desc`, not `contentDesc`).
    - Exception classes must end with the `Error` suffix (e.g., `DeviceIsSecureError`).
- **Typing**:
    - Use strict type hints wherever possible.
    - Use `from __future__ import annotations` for forward references.
- **XML Processing**:
    - Prefer `lxml.etree` over the standard `xml.etree.ElementTree` for better XPath support.
    - Standard import: `from lxml import etree`.
- **Imports**:
    - Keep imports sorted and organized using `ruff`.
- **Error Handling**:
    - When re-raising exceptions, use `raise ... from err` or `raise ... from None` to maintain clean tracebacks.
