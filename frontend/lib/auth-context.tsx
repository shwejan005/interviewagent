"use client";

/**
 * Auth context: the one place that knows the current actor, token, and
 * active organization. Every authenticated page reads from `useAuth()`
 * rather than re-deriving this state, so a login/logout/org-switch is
 * visible everywhere in one render.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, clearToken, getActiveOrgId, getToken, setActiveOrgId as persistActiveOrgId, setToken } from "./api";
import type { Actor } from "./types";

type AuthContextValue = {
  actor: Actor | null;
  loading: boolean;
  activeOrgId: number | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  refreshActor: () => Promise<void>;
  switchOrg: (orgId: number | null) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [actor, setActor] = useState<Actor | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeOrgId, setActiveOrgIdState] = useState<number | null>(null);

  const refreshActor = useCallback(async () => {
    if (!getToken()) {
      setActor(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<Actor>("/auth/me");
      setActor(me);
    } catch (err) {
      // An expired/invalid token must not strand the app in a loading state.
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
      }
      setActor(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setActiveOrgIdState(getActiveOrgId());
    refreshActor();
  }, [refreshActor]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string }>("/auth/login", { email, password }, { skipAuth: true });
    setToken(res.access_token);
    await refreshActor();
  }, [refreshActor]);

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    const res = await api.post<{ access_token: string }>(
      "/auth/register",
      { email, password, full_name: fullName },
      { skipAuth: true },
    );
    setToken(res.access_token);
    await refreshActor();
  }, [refreshActor]);

  const logout = useCallback(() => {
    clearToken();
    persistActiveOrgId(null);
    setActiveOrgIdState(null);
    setActor(null);
  }, []);

  const switchOrg = useCallback(async (orgId: number | null) => {
    persistActiveOrgId(orgId);
    setActiveOrgIdState(orgId);
    await refreshActor();
  }, [refreshActor]);

  const value = useMemo(
    () => ({ actor, loading, activeOrgId, login, register, logout, refreshActor, switchOrg }),
    [actor, loading, activeOrgId, login, register, logout, refreshActor, switchOrg],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
