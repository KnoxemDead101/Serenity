---
name: Browser validation workflow
description: Replit validation registration and the ordinary Run button can become coupled.
---

Register the browser suite as a named validation, but do not include it as a
parallel task in the ordinary app Run workflow.

**Why:** Registering a named test validation also added the test workflow to
the Run button in this project. That would launch Chromium every time the app
starts, even when no validation was requested.

**How to apply:** When changing validation commands, inspect whether the
project Run workflow gained a test task. If so, keep the independent named
validation and remove only the Run-button invocation through the validated
Replit config replacement flow.

That replacement accepts an absolute workspace temporary TOML path under the
`tempFilePath` argument.

**Why:** Direct patches to managed `.replit` are rejected; the replacement
callback validates the complete configuration before applying it.

**How to apply:** Write a sibling temporary file, then call
`verifyAndReplaceDotReplit({tempFilePath: absolutePath})`. Keep the named test
validation independent of the ordinary Run group.

Run the complete publishing gate as a background shell task when using the
agent's shell tools.

**Why:** The required PostgreSQL/browser suite exceeded the foreground shell's
five-minute limit even while continuing to pass. A shell timeout is not a test
failure or a completed validation result.

**How to apply:** Start one background gate, monitor its completion, and retain
its exit status and final summary. Do not publish or claim a pass from partial
progress output.