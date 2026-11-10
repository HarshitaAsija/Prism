import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import api from "../api/client";
const AuthContext = createContext(null);
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    // Discard legacy browser-only demo sessions. The server is authoritative.
    localStorage.removeItem("prism_user");
    let active = true;
    api
      .get("/auth/me")
      .then((r) => {
        if (active) setUser(r.data);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const expired = () => setUser(null);
    window.addEventListener("prism-session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("prism-session-expired", expired);
    };
  }, []);
  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setUser(data);
    return data;
  }, []);
  const register = useCallback(async (name, email, password, role) => {
    const { data } = await api.post("/auth/register", {
      name,
      email,
      password,
      role,
    });
    setUser(data);
    return data;
  }, []);
  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
      setUser(null);
    } catch (error) {
      if (error.response?.status === 401) setUser(null);
      else window.alert("Sign out failed. Please try again.");
    }
  }, []);
  if (loading)
    return (
      <div className="p-10 text-center text-slate-300" role="status">
        Checking your session…
      </div>
    );
  return (
    <AuthContext.Provider
      value={{ user, login, register, logout, isAuthenticated: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
