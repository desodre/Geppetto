# Contributing to Geppetto

Geppetto targets Android device and system QA. Start with an issue on the
[Geppetto Roadmap](https://github.com/users/desodre/projects/10), agree on its Done when,
and move that issue to In Progress when implementation starts.

## Development environment

Use Python 3.12 or 3.13. Install Android SDK platform tools for integration work.
Unit tests replace adb; they do not need a device.

```bash
uv sync --frozen --group dev --group docs
uv run ruff check src tests integration scripts examples/recipes
uv run ruff format --check src tests integration scripts examples/recipes
uv run mypy src
uv run pytest
uv run --group docs mkdocs build --strict
uv build
```

Optional analyzers/hardware remain optional. Use `--all-extras` only when working
on those modules. Docs build from static Python sources without importing them.

Run integration only on an emulator or a device whose owner authorized automation:

```bash
uv run pytest integration --serial emulator-5554 --geppetto-artifacts=on-failure
```

The first `Device(serial)` installs the uiautomator2 agent. Device operations can
change apps, settings and boot state. Always select a serial explicitly for lab work.

## Pull requests

Branch from main using `feat/<slug>-<issue>`, `fix/<slug>-<issue>`, `docs/...` or `ci/...`.
Use English Conventional Commits and explain why. Submit a PR to main; never push
straight to main. Request maintainer direction before pushing, tagging or publishing.

Tests cover happy paths and the motivating failure. Add a real-emulator integration
case when only a device proves the behavior. Preserve shell quoting, secrets, lazy
extras and strict typing; see [AGENTS.md](https://github.com/desodre/Geppetto/blob/main/AGENTS.md). Update CHANGELOG and usage docs.

CI runs Python 3.12/3.13 checks and API 34 integration for every PR to main.
The dev workflow reuses that same pipeline. Release validation additionally runs
the API 26 compatibility smoke. A missing/entirely skipped integration run fails.

Only reference **completed** issues with `Refs #N`, `Closes #N` or a commit suffix
`(#N)`: the merge action closes those issues and their subissues recursively.
Use a normal URL or `Part of #N` for unfinished parent work.

<!-- --8<-- [start:versioning] -->
## Versioning and public API

Geppetto follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html):

| Release | Allowed change |
| --- | --- |
| PATCH | Backward-compatible bug fixes and clarifications |
| MINOR | Backward-compatible features and deprecation announcements |
| MAJOR | Incompatible API changes, removals, or reductions in supported environments |

The public contract includes `geppetto.__all__`, APIs documented in README/site,
documented CLI commands and exit behavior, pytest fixtures/options/markers and
artifact formats explicitly documented as stable. Private underscore helpers are
internal. Other modules are not automatically stable merely because they import.

### Deprecation

A deprecated API must keep working for at least one complete published minor release.
Emit `DeprecationWarning` identifying the replacement and starting version, add a
CHANGELOG entry and migration instructions, and remove it only in a subsequent major.
For example: announce in 2.2, keep it in 2.3, remove no earlier than 3.0.
The warning clock starts at a published release, not an unreleased main commit.

Implementers call `geppetto._deprecation.warn_deprecated(old, new, since)` from the
public function so the warning points to the user's call site. Test its location
when adding wrappers. Existing `Direction.Up` and `Direction.Down` aliases continue
to work without new warnings; this policy does not deprecate additional APIs.

### Supported environments

| Environment | Support and evidence |
| --- | --- |
| Python 3.12 and 3.13 | Supported; lint/types/unit checks in CI |
| Python below 3.12 | Unsupported; rejected by package metadata |
| Newer Python | Not yet certified; `>=3.12` metadata is not a guarantee about future releases |
| Android API 34 / Android 14 | Full integration target on Linux x86_64 emulators |
| Android API 26 / Android 8 | Supported minimum; compatibility smoke, repeated before releases |
| Other Android API 26+ builds | Intended compatibility; only the listed matrix has automated evidence |
| OEM devices, other host OSes | Report compatibility with model/build/tool versions; not certified by the emulator job |
| Fastboot, root, hardware | Require matching device capabilities and optional dependencies; outside the emulator guarantee |

API 26 was validated with the 13-test compatibility smoke; API 34 runs the full suite.
The integration workflow supports manual API 26 smoke runs; publication requires that job to pass.
Device permissions, OEM restrictions and optional extras may limit individual features.
Crash-injection tests using `am crash` require Android 13+ and are not part of the
API 26 smoke; parsing crash logs itself does not require Android 13.

The package ships `geppetto/py.typed` for type checkers. Optional features require their
extras; base installation and static documentation must work without hardware packages.

### Release checklist

1. Confirm the issues actually completed; leave deployment-dependent work open.
2. Update `__version__` in `src/geppetto/__init__.py` (the only version source).
3. Move Unreleased changelog entries into the matching version and review migrations.
4. Pass Python checks, API 34 integration, API 26 smoke and strict documentation build.
5. Build wheel/sdist; confirm `geppetto/py.typed` and install the wheel in a clean environment.
6. After maintainer authorization, create a matching `vX.Y.Z` tag and push it.
7. Existing OIDC publishing waits for CI and rejects a tag differing from `__version__`.
8. Verify PyPI installation and public documentation, and retain links to validation runs.

Do not reuse a published version. Documentation on main may describe unreleased features;
label them accordingly instead of suggesting that an older PyPI release contains them.
<!-- --8<-- [end:versioning] -->

## Documentation maintenance

Serve locally with `uv run --group docs mkdocs serve` and build with `--strict`.
Examples are included from executable source files. Keep CONTRIBUTING and CHANGELOG as
their canonical sources; the site includes them, rather than maintaining manual copies.

Material for MkDocs announces end of life on 5 May 2027. Track migration before then;
keep Markdown portable and avoid custom theme dependencies. See the
[upstream announcement](https://squidfunk.github.io/mkdocs-material/getting-started/)
and [migration tracking issue](https://github.com/desodre/Geppetto/issues/63).
