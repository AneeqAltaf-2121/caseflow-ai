"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

// This is the redirect_uri registered with Google (see .env.example's
// OAUTH_REDIRECT_URL) — Google sends the browser here with `?code=...`
// after the user consents, and we hand that code to the backend to
// exchange for our own session tokens (see lib/auth-context.tsx).
function GoogleCallbackInner() {
  const { completeGoogleLogin } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const oauthError = searchParams.get("error");
    if (oauthError) {
      setError(`Google sign-in was cancelled or failed (${oauthError}).`);
      return;
    }
    if (!code) {
      setError("Missing authorization code from Google.");
      return;
    }
    completeGoogleLogin(code)
      .then(() => router.replace("/dashboard"))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Sign-in failed."));
  }, [searchParams, completeGoogleLogin, router]);

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      {error ? (
        <div className="max-w-sm text-center">
          <p className="text-sm font-medium text-red-600 dark:text-red-400">{error}</p>
          <a href="/login" className="mt-3 inline-block text-sm underline">
            Back to sign in
          </a>
        </div>
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Completing sign-in…</p>
      )}
    </div>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Completing sign-in…</p>
        </div>
      }
    >
      <GoogleCallbackInner />
    </Suspense>
  );
}
