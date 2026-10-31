# Geppetto

Typed Python automation for Android device labs: one `Device` facade for ADB,
Fastboot, UIAutomator2 and OS services, with pytest failure artifacts.

!!! note "Documentation from main"
    This site follows main, including unreleased changes. The [changelog](changelog.md)
    distinguishes them from published releases. Use a checkout for unreleased examples.

Start with [installation](getting-started.md), run the [login recipe](recipes/login.md),
or explore the [Device reference](reference/device.md).

Geppetto ships **`py.typed`**, supports strict type checking and keeps hardware/image
analysis in optional extras. It targets system and device QA, including multi-device
labs, boot state and OS features.

## Practical workflows

- [pytest fixtures and automatic failure artifacts](guides/pytest.md)
- [Screen inspection and recording Python code](guides/inspector.md)
- [Live logcat and watched crashes](guides/logcat-and-crashes.md)
- [Two-device tests](recipes/two-devices.md)
- [Versioning and support commitments](policies/versioning.md)
