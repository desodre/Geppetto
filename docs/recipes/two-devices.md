# Two devices

Start two emulators (or use two lab devices whose owners authorized automation) and name both
serials. Each device keeps its own output folder; a `devices` test captures all selected devices.

```bash
uv run pytest examples/recipes/two_devices.py --serial emulator-5554 --serial emulator-5556
```

```python
--8<-- "examples/recipes/two_devices.py"
```

The example skips if fewer than two were selected. It does not prove simultaneous execution:
the calls run sequentially, making device attribution clear. Use two dedicated AVDs and avoid
sharing them with other tests. This recipe is validated separately from single-emulator PR CI.
