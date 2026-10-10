import { createContext, useContext, useState, type ReactNode } from "react";

export type User = {
  name: string;
  email: string;
  picture?: string;
  token: string; // Google ID token — send this to the backend later
};

type AuthContextType = {
  user: User | null;
  loginWithGoogle: (credential: string) => void;
  loginAsGuest: () => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);
const STORAGE_KEY = "sonar_user";

// Reads the name/email/picture out of the Google ID token (a JWT).
// NOTE: this only DISPLAYS the user. The backend must VERIFY the token before trusting it.
function decodeGoogleToken(credential: string): User {
  const payload = credential.split(".")[1];
  const json = JSON.parse(decodeURIComponent(
    atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
      .split("")
      .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
      .join("")
  ));
  return { name: json.name, email: json.email, picture: json.picture, token: credential };
}

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(loadUser);

  function save(u: User | null) {
    setUser(u);
    try {
      if (u) localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
      else localStorage.removeItem(STORAGE_KEY);
    } catch { /* ignore */ }
  }

  const value: AuthContextType = {
    user,
    loginWithGoogle: (credential) => save(decodeGoogleToken(credential)),
    loginAsGuest: () => save({ name: "Guest", email: "guest@local", token: "" }),
    logout: () => save(null),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}