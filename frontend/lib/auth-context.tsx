"use client";

/**
 * Auth context: the one place that knows the current actor, token, and
 * active organization. Every authenticated page reads from `useAuth()`
 * rather than re-deriving this state, so a login/logout/org-switch is
 * visible everywhere in one render.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import SessionExpiryDialog from "../app/components/SessionExpiryDialog";
import {
  api,
  ApiError,
  clearToken,
  getActiveOrgId,
  getToken,
  getTokenExpiresAt,
  setActiveOrgId as persistActiveOrgId,
  setToken,
} from "./api";
import type { Actor } from "./types";

const SESSION_PROMPT_WINDOW_MS = 15 * 60 * 1000;
const SESSION_CHECK_INTERVAL_MS = 30 * 1000;

type TokenResponse = {
  access_token: string;
  expires_in: number;
};

type AuthContextValue = {
  actor: Actor | null;
  loading: boolean;
  activeOrgId: number | null;
  sessionPromptOpen: boolean;
  sessionExpiresAt: number | null;
  sessionRefreshing: boolean;
  login: (email: string, password: string) => Promise<Actor>;
  register: (email: string, password: string, fullName: string) => Promise<Actor>;
  logout: () => void;
  refreshActor: () => Promise<Actor | null>;
  extendSession: () => Promise<void>;
  dismissSessionPrompt: () => void;
  switchOrg: (orgId: number | null) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [actor, setActor] = useState<Actor | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeOrgId, setActiveOrgId] = useState<number | null>(null);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<number | null>(null);
  const [sessionPromptOpen, setSessionPromptOpen] = useState(false);
  const [sessionRefreshing, setSessionRefreshing] = useState(false);
  const promptedForExpiry = useRef<number | null>(null);

  const refreshActor = useCallback(async () => {
    if (!getToken()) {
      setActor(null);
      setSessionExpiresAt(null);
      setSessionPromptOpen(false);
      setLoading(false);
      return null;
    }
    try {
      const me = await api.get<Actor>("/auth/me");
      setActor(me);
      const storedOrgId = getActiveOrgId();
      const storedMembership = me.memberships.find((membership) => membership.org_id === storedOrgId);
      const resolvedOrgId = storedMembership?.org_id ?? me.memberships[0]?.org_id ?? null;
      persistActiveOrgId(resolvedOrgId);
      setActiveOrgId(resolvedOrgId);
      return me;
    } catch (err) {
      // An expired/invalid token must not strand the app in a loading state.
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        setSessionExpiresAt(null);
        setSessionPromptOpen(false);
      }
      setActor(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setActiveOrgId(getActiveOrgId());
    setSessionExpiresAt(getTokenExpiresAt());
    void refreshActor();
  }, [refreshActor]);

  useEffect(() => {
    if (!actor || actor.impersonated_by || !sessionExpiresAt) return;

    const checkExpiry = () => {
      const remaining = sessionExpiresAt - Date.now();
      if (remaining <= 0) {
        setSessionPromptOpen(false);
        return;
      }

      if (remaining <= SESSION_PROMPT_WINDOW_MS && promptedForExpiry.current !== sessionExpiresAt) {
        promptedForExpiry.current = sessionExpiresAt;
        setSessionPromptOpen(true);
      }
    };

    checkExpiry();
    const timer = window.setInterval(checkExpiry, SESSION_CHECK_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [actor, sessionExpiresAt]);

  const login = useCallback(async (email: string, password: string): Promise<Actor> => {
    const res = await api.post<TokenResponse>("/auth/login", { email: email.trim(), password }, { skipAuth: true });
    setToken(res.access_token, res.expires_in);
    setSessionExpiresAt(getTokenExpiresAt());
    promptedForExpiry.current = null;
    const resolvedActor = await refreshActor();
    if (!resolvedActor) throw new Error("Unable to load the signed-in account.");
    return resolvedActor;
  }, [refreshActor]);

  const register = useCallback(async (email: string, password: string, fullName: string): Promise<Actor> => {
    const res = await api.post<TokenResponse>(
      "/auth/register",
      { email: email.trim(), password, full_name: fullName.trim() },
      { skipAuth: true },
    );
    setToken(res.access_token, res.expires_in);
    setSessionExpiresAt(getTokenExpiresAt());
    promptedForExpiry.current = null;
    const resolvedActor = await refreshActor();
    if (!resolvedActor) throw new Error("Unable to load the new account.");
    return resolvedActor;
  }, [refreshActor]);

  const extendSession = useCallback(async () => {
    setSessionRefreshing(true);
    try {
      const res = await api.post<TokenResponse>("/auth/refresh");
      setToken(res.access_token, res.expires_in);
      setSessionExpiresAt(getTokenExpiresAt());
      promptedForExpiry.current = null;
      setSessionPromptOpen(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        setActor(null);
        setSessionExpiresAt(null);
        setSessionPromptOpen(false);
      }
      throw err;
    } finally {
      setSessionRefreshing(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    persistActiveOrgId(null);
    setActiveOrgId(null);
    setActor(null);
    setSessionExpiresAt(null);
    setSessionPromptOpen(false);
  }, []);

  const dismissSessionPrompt = useCallback(() => {
    setSessionPromptOpen(false);
  }, []);

  const switchOrg = useCallback(async (orgId: number | null) => {
    persistActiveOrgId(orgId);
    setActiveOrgId(orgId);
    await refreshActor();
  }, [refreshActor]);

  const value = useMemo(
    () => ({
      actor,
      loading,
      activeOrgId,
      sessionPromptOpen,
      sessionExpiresAt,
      sessionRefreshing,
      login,
      register,
      logout,
      refreshActor,
      extendSession,
      dismissSessionPrompt,
      switchOrg,
    }),
    [
      actor,
      loading,
      activeOrgId,
      sessionPromptOpen,
      sessionExpiresAt,
      sessionRefreshing,
      login,
      register,
      logout,
      refreshActor,
      extendSession,
      dismissSessionPrompt,
      switchOrg,
    ],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <SessionExpiryDialog
        open={sessionPromptOpen}
        expiresAt={sessionExpiresAt}
        loading={sessionRefreshing}
        onExtend={extendSession}
        onDismiss={dismissSessionPrompt}
      />
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
