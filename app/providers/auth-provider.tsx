"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { supabase } from "@/lib/supabase";
import type { Session } from "@supabase/supabase-js";

interface AuthState {
  session: Session | null;
  email: string | null;
  credits: number;
  token: string | null;
  loading: boolean;
  setCredits: (c: number) => void;
}

const AuthContext = createContext<AuthState>({
  session: null,
  email: null,
  credits: 0,
  token: null,
  loading: true,
  setCredits: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [credits, setCredits] = useState(0);
  const [loading, setLoading] = useState(true);
  const fetchingRef = useRef(false);

  const fetchCredits = useCallback(async (token: string) => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${apiUrl}/api/credits`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCredits(data.credits);
      }
    } catch {
      // API not reachable
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    let lastToken = "";

    const handleSession = (newSession: Session | null) => {
      setSession(newSession);
      setLoading(false);
      const token = newSession?.access_token;
      if (token && token !== lastToken) {
        lastToken = token;
        fetchCredits(token);
      }
      if (!token) {
        setCredits(0);
      }
    };

    supabase.auth.getSession().then(({ data: { session: s } }) => handleSession(s));

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => handleSession(s));

    return () => subscription.unsubscribe();
  }, [fetchCredits]);

  const value: AuthState = {
    session,
    email: session?.user?.email || null,
    credits,
    token: session?.access_token || null,
    loading,
    setCredits,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
