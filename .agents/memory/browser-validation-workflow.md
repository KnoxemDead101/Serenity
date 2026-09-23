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