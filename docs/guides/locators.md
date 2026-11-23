# Locators and `expect()`

Locators are available in main; check the [changelog](../changelog.md) before using a published
PyPI release.

`device.get(by, value)` returns a lazy [`Locator`](../reference/locator.md). Nothing touches the
device until you act on it or read it; then Geppetto dumps the UI hierarchy and polls it until the
element is in the state the action needs. No `sleep`, no manual wait before each tap.

```python
from geppetto import By, Device, expect

device = Device("emulator-5554")

device.get(By.ID, "com.app:id/username").fill("demo")
device.get(By.ID, "com.app:id/password").fill("secret", log_text=False)
device.get(By.TEXT, "Login").click()
expect(device.get(By.TEXT, "Welcome, demo!")).to_be_visible()
```

## Auto-waiting actions

Every action waits until the **first match** is visible (non-empty bounds) and enabled, then acts
on its center. Each takes `timeout=` (seconds); the default is the device's `default_timeout`
(10 s, set with `Device(serial, default_timeout=20)`).

| Action | What it does |
|---|---|
| `click()` | Taps the center of the element. |
| `long_press(duration=1.0)` | Presses the center for `duration` seconds. |
| `fill(text, log_text=True)` | Taps the field, deletes its current text and types `text`. |
| `type_text(text, log_text=True)` | Taps the element and types `text` after what is already there. |
| `swipe_to(target, duration=1.0)` | Swipes from this element to another `Locator` (also waited for) or an `(x, y)` point. |

Pass `log_text=False` for passwords, PINs and tokens: the text stays out of the logs.
Spaces are encoded for `input text` for you.

When the element does not become actionable in time, the action raises
`DeviceTimeoutError` with the last state seen:

```text
Timeout after 10s waiting for device.get(By.TEXT, 'Login') to be visible and enabled;
last seen: android.widget.Button text='Login' enabled=False checked=False bounds=...
```

### Reads

| Read | Waits? | Returns |
|---|---|---|
| `widget(timeout=None)` | yes, until present | the first matching `Widget`, children filled in |
| `text` | yes, until present | the first match's `text` |
| `wait_for(state="visible", timeout=None)` | yes | the `Widget` (`None` for `"hidden"`); states: `"visible"`, `"hidden"`, `"enabled"`, `"attached"` |
| `all()` | no | every match right now |
| `count()`, `is_visible()`, `is_enabled()`, `is_checked()` | no | the answer right now |

Prefer `expect()` over `assert loc.is_visible()`: the non-waiting reads answer once and are
subject to the same timing races as `sleep`-based code.

## Selectors

Strategies come from `By`: `By.ID` (`resource-id`), `By.TEXT`, `By.CONTENT_DESC`, `By.CLASS`
and `By.XPATH`.

```python
import re

device.get(By.TEXT, "Wi-Fi")                          # exact attribute value
device.get(By.TEXT, "wi-fi", exact=False)             # case-insensitive substring
device.get(By.TEXT, re.compile(r"^Wi.?Fi$"))          # regex (re.search)
device.get(By.XPATH, "//node[@resource-id='com.app:id/row']")
```

`exact=False` and compiled patterns apply to attribute strategies; `By.XPATH` takes only a
string expression (a regex raises `TypeError`) evaluated on the hierarchy dump (`<node>` elements, as in `geppetto inspect`).
Never build XPath by interpolating untrusted text; use a regex or `exact=False` instead.

### Chaining

Every refinement returns a **new** locator (the original is unchanged) and does no I/O.

| Method | Keeps |
|---|---|
| `.get(by, value, exact=True)` | descendants of the current matches that match |
| `.filter(by, value, exact=True)` | current matches that also match on the same node |
| `.filter(has=other)` | current matches containing a descendant matched by `other` |
| `.within(other)` | matches inside the first match of `other` |
| `.below(other)`, `.above(other)` | matches under / over the first match of `other`, closest first |
| `.right_of(other)`, `.left_of(other)` | matches to the right / left of `other`, closest first |
| `.nth(i)` | the match at index `i` (`-1` is the last) |
| `.first`, `.last` | `.nth(0)`, `.nth(-1)` |

```python
# The Switch on the row whose title is "Bluetooth".
row = device.get(By.ID, "android:id/content").get(By.CLASS, "android.widget.LinearLayout")
row.filter(has=device.get(By.TEXT, "Bluetooth")).get(By.CLASS, "android.widget.Switch").click()

# The text field closest under the "Email" label.
email = device.get(By.TEXT, "Email")
device.get(By.CLASS, "android.widget.EditText").below(email).fill("me@example.com")

# Scope to a dialog, then take the last button.
dialog = device.get(By.ID, "android:id/parentPanel")
device.get(By.CLASS, "android.widget.Button").within(dialog).last.click()
```

Matches keep document order, except after a relative step (`below`, `above`, `right_of`,
`left_of`), which sorts by distance on that side's axis and then by offset on the other axis.
When several widgets match, actions and assertions use the first one; narrow the locator rather
than relying on order when the screen can change.

## Retrying assertions with `expect()`

`expect(locator, timeout=None, poll=0.25)` re-dumps the hierarchy every `poll` seconds until the
assertion holds or `timeout` expires (default: the device's `default_timeout`). Each assertion
also takes its own `timeout=`.

```python
from geppetto import expect

expect(device.get(By.ID, "com.app:id/error")).to_have_text("Invalid password")
expect(device.get(By.ID, "com.app:id/error")).to_have_text(re.compile(r"invalid", re.I))
expect(device.get(By.TEXT, "Signing in…")).to_be_hidden(timeout=30)
expect(device.get(By.ID, "com.app:id/row")).to_have_count(3)
expect(device.get(By.TEXT, "Remember me")).not_.to_be_checked()
```

| Assertion | Holds when |
|---|---|
| `to_be_visible()` / `to_be_hidden()` | the first match has / has no box on screen (no match counts as hidden) |
| `to_be_enabled()` / `to_be_disabled()` | the first match is enabled / disabled |
| `to_be_checked(checked=True)` | the first match's `checked` equals `checked` |
| `to_be_selected(selected=True)` | the first match's `selected` equals `selected` |
| `to_be_focused()` | the first match is focused |
| `to_have_text(expected, exact=True)` | text equals `expected` (stripped), contains it case-insensitively with `exact=False`, or matches a regex |
| `to_contain_text(expected)` | shortcut for `to_have_text(expected, exact=False)` |
| `to_have_content_desc(expected, exact=True)` | same rules as `to_have_text`, on `content-desc` |
| `to_have_count(n)` | exactly `n` matches |

`.not_` negates any assertion and keeps retrying until the opposite holds:
`expect(loc).not_.to_be_visible()` waits for the element to go away. State and content
assertions (`not_.to_be_enabled()`, `not_.to_have_text(...)`…) still require a matching element
so an absent widget never passes by accident.

### `ExpectationError`

A failed assertion raises [`ExpectationError`](../reference/exceptions.md), a `GeppettoError`
that is also an `AssertionError`, so pytest reports it as a failed assertion (and the
[pytest plugin](pytest.md) saves its failure artifacts). The message carries the expectation and
the last observed state:

```text
Expected device.get(By.ID, 'com.app:id/error') to be text 'Invalid password' (waited 10s);
last seen: text 'Signing in…'
```

## Migrating from `await_widget` / `find_widget`

`Device.get()` replaces the manual `await_widget` + `click` pattern ([#16](https://github.com/desodre/Geppetto/issues/16)).

!!! note "Nothing to change today"
    `Device.await_widget()` and `WindowDump.find_widget()` keep working and emit **no warning**
    yet. Any removal follows the [versioning policy](../policies/versioning.md): a
    `DeprecationWarning` and CHANGELOG entry first, at least one complete published minor release
    with the warning, and removal no earlier than the next major (3.0). Migrate at your own pace.

| Before | After |
|---|---|
| `device.click(device.await_widget(By.TEXT, "Login"))` | `device.get(By.TEXT, "Login").click()` |
| `w = device.await_widget(By.ID, rid, timeout=15)` | `w = device.get(By.ID, rid).widget(timeout=15)` |
| `device.get_window_dump().find_widget(By.XPATH, xp)` | `device.get(By.XPATH, xp).widget()` |
| `device.click(field); device.input_text("x")` | `device.get(...).fill("x")` (or `.type_text("x")` to append) |
| `assert device.await_widget(By.ID, rid).text == "x"` | `expect(device.get(By.ID, rid)).to_have_text("x")` |
| `time.sleep(2)` before a lookup | nothing: actions and `expect()` wait |

Differences to keep in mind while migrating:

- **Lazy.** `device.get()` returns immediately; the lookup happens at the action. Build locators
  once (for example in a page object) and reuse them: each use re-resolves on the current screen.
- **Actionable, not just present.** Actions wait for visible *and* enabled; `await_widget` only
  waited for existence. Use `widget()` when you need the old "present" semantics.
- **Errors.** A missing element raises `DeviceTimeoutError` from actions and `ExpectationError`
  from `expect()`, both `GeppettoError` subclasses, with the last observed state in the message.
- **Timeouts.** `await_widget(timeout=...)` defaulted per call; locators default to
  `Device.default_timeout` and accept `timeout=` on every action, read and assertion.

[`geppetto inspect`](inspector.md) already records locator code
(`device.get(By.ID, ...).click()`), so new recordings need no migration.
