const clerkScriptUrl = "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js";
const clerkUiScriptUrl = "https://cdn.jsdelivr.net/npm/@clerk/ui@1.34.0/dist/ui.browser.js";

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Unable to load sign-in."));
    document.head.appendChild(script);
  });
}

async function loadClerk() {
  const configResponse = await fetch("/serenity-api/auth/config");
  const config = await configResponse.json();
  if (!config.publishable_key) {
    throw new Error("Sign-in is not configured.");
  }

  await loadScript(clerkUiScriptUrl);
  const script = document.createElement("script");
  script.src = clerkScriptUrl;
  script.setAttribute("data-clerk-publishable-key", config.publishable_key);
  await new Promise((resolve, reject) => {
    script.onload = resolve;
    script.onerror = () => reject(new Error("Unable to load sign-in."));
    document.head.appendChild(script);
  });

  await window.Clerk.load({
    ui: { ClerkUI: window.__internal_ClerkUICtor },
  });
  return window.Clerk;
}

async function establishSerenitySession(clerk) {
  if (!clerk.session) return false;
  const token = await clerk.session.getToken();
  if (!token) return false;
  const response = await fetch("/serenity-api/auth/session", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("The sign-in session could not be created.");
  const next = new URLSearchParams(window.location.search).get("next") || "/";
  window.location.assign(safeSignInReturnPath(next));
  return true;
}

function safeSignInReturnPath(value) {
  if (!value.startsWith("/") || value.startsWith("//") ||
      /[\\\u0000-\u001f\u007f]/.test(value)) return "/";
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin &&
      target.pathname !== "/sign-in" && target.pathname !== "/sign-out"
      ? target.pathname + target.search : "/";
  } catch {
    return "/";
  }
}

async function showSignIn() {
  const error = document.getElementById("auth-error");
  try {
    const clerk = await loadClerk();
    if (await establishSerenitySession(clerk)) return;
    clerk.mountSignIn(document.getElementById("clerk-sign-in"), {
      afterSignInUrl: window.location.href,
      afterSignUpUrl: window.location.href,
    });
    clerk.addListener(async () => {
      try {
        await establishSerenitySession(clerk);
      } catch (sessionError) {
        error.textContent = sessionError.message;
        error.hidden = false;
      }
    });
  } catch (loadError) {
    error.textContent = loadError.message;
    error.hidden = false;
  }
}

async function signOutOfSerenity() {
  // Clear idle financial tabs immediately, even if loading Clerk is slow.
  // No tokens, user identifiers, or drafts are sent or stored.
  try {
    const channel = new BroadcastChannel("serenity-session");
    channel.postMessage("signed-out");
    channel.close();
  } catch {
    // Restricted browsers rely on the visibility-time server check.
  }
  try {
    // Clear our cookie before loading the third-party SDK, so a CDN outage
    // cannot prevent Serenity's own sign-out request.
    await fetch("/serenity-api/auth/session", { method: "DELETE" });
    const clerk = await loadClerk();
    await clerk.signOut();
  } catch {
    // The sign-in page provides recovery if the auth service is unavailable.
  } finally {
    window.location.assign("/sign-in");
  }
}

if (document.getElementById("clerk-sign-in")) {
  showSignIn();
}