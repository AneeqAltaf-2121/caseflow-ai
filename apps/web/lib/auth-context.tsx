"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import { clearTokens, getAccessToken, setTokens } from "./tokens";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  /** Undetermined-yet vs. determined-absent, so pages can show a loading
   * state instead of flashing the login page before the first /auth/me
   * check resolves. */
  status: "loading" | "authenticated" | "unauthenticated";
  loginWithMock: (email: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  completeGoogleLogin: (code: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setStatus("unauthenticated");
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      setStatus("authenticated");
    } catch {
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const loginWithMock = useCallback(
    async (email: string) => {
      const tokens = await api.exchangeCode("mock", email);
      setTokens(tokens.access_token, tokens.refresh_token);
      await refreshUser();
    },
    [refreshUser]
  );

  const loginWithGoogle = useCallback(async () => {
    // The frontend owns the OAuth redirect URI (/login/callback — see that
    // page): Google sends the browser back here with a `code`, and we hand
    // that code to the backend to exchange for our own session tokens.
    // See docs/decisions/004-authentication.md.
    const { authorize_url } = await api.loginUrl("google");
    window.location.href = authorize_url;
  }, []);

  const completeGoogleLogin = useCallback(
    async (code: string) => {
      const tokens = await api.exchangeCode("google", code);
      setTokens(tokens.access_token, tokens.refresh_token);
      await refreshUser();
    },
    [refreshUser]
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, status, loginWithMock, loginWithGoogle, completeGoogleLogin, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
