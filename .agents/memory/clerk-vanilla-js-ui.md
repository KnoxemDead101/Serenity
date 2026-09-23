---
name: Clerk vanilla JavaScript UI loading
description: How Serenity's plain HTML frontend must load Clerk's current prebuilt sign-in UI.
---

Clerk's current browser SDK can load without its prebuilt UI components when used from plain HTML. Load the matching `@clerk/ui` browser bundle before `@clerk/clerk-js`, then pass `window.__internal_ClerkUICtor` through `clerk.load({ ui: { ClerkUI } })`.

**Why:** Calling `mountSignIn` without this setup renders a runtime error instead of the sign-in form.

**How to apply:** Keep the UI and Clerk CDN versions aligned, and recheck this initialization when upgrading either package.