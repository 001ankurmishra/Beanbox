'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState
} from 'react';
import { authApi } from '@/lib/api/endpoints';
import { LoginResult, User } from '@/types/api';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  googleOAuthEnabled: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verify2faLogin: (challengeToken: string, code: string) => Promise<User>;
  signup: (data: {
    name: string;
    email: string;
    password: string;
    phone?: string;
  }) => Promise<User>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);

  const refreshUser = useCallback(async () => {
    try {
      const res = await authApi.me();
      setUser(res.user);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
    authApi
      .providers()
      .then((res) => setGoogleOAuthEnabled(Boolean(res.googleOAuthEnabled)))
      .catch(() => setGoogleOAuthEnabled(false));
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    if (!res.requiresTwoFactor && 'user' in res) {
      setUser(res.user);
    }
    return res;
  }, []);

  const verify2faLogin = useCallback(async (challengeToken: string, code: string) => {
    const res = await authApi.verify2faLogin({ challengeToken, code });
    setUser(res.user);
    return res.user;
  }, []);

  const signup = useCallback(
    async (data: {
      name: string;
      email: string;
      password: string;
      phone?: string;
    }) => {
      const res = await authApi.signup(data);
      setUser(res.user);
      return res.user;
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const logoutAll = useCallback(async () => {
    try {
      await authApi.logoutAll();
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        googleOAuthEnabled,
        login,
        verify2faLogin,
        signup,
        logout,
        logoutAll,
        refreshUser
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
