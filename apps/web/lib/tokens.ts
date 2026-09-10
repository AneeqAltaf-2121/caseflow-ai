// Session tokens live in localStorage: this is a client-only SPA (no
// server components read auth state), so there's no CSRF-relevant cookie
// to protect — the tradeoff is that tokens are readable by any script that
// runs on the page, which is why the backend keeps access tokens
// short-lived (see docs/decisions/004-authentication.md).

const ACCESS_KEY = "caseflow.access_token";
const REFRESH_KEY = "caseflow.refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  window.localStorage.setItem(ACCESS_KEY, accessToken);
  window.localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}
