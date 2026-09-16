import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, refreshSession, setAccessToken, setSessionListener } from "../lib/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    setSessionListener((session) => setUser(session?.user ?? null));
    // Restore the session from the refresh cookie on page load.
    refreshSession().then((session) => {
      setUser(session?.user ?? null);
      setStatus("ready");
    });
  }, []);

  const login = useCallback(async (email, password) => {
    const session = await api("/auth/login", { method: "POST", body: { email, password }, auth: false });
    setAccessToken(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", auth: false });
    } finally {
      setAccessToken(null);
      setUser(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo(() => ({ user, status, login, logout, setUser }), [user, status, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
