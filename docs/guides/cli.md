# Command line

```bash
geppetto devices --json
geppetto doctor -s emulator-5554
geppetto shot -s emulator-5554 -o screen.png
geppetto record -s emulator-5554 -t 10 -o screen.mp4
geppetto emulator list
geppetto emulator start My_AVD --headless
geppetto emulator stop emulator-5554
geppetto emulator snapshot save clean -s emulator-5554
geppetto pair 192.168.0.10:40111 123456
geppetto connect 192.168.0.10:37000
geppetto disconnect 192.168.0.10:37000
```

Use `geppetto --help` and each subcommand's `--help` for flags. Single-device commands select
`-s/--serial`, then `GEPPETTO_SERIAL`, then the only ready device. Record is limited to
180 seconds by Android. `doctor` explains failed checks and fixes; failures exit with 1.
QR pairing (`geppetto pair --qr`) requires the `[cli]` extra.
