import { create } from 'zustand';
import { apiFetch, getToken, setToken } from '../api/client';

const AUTH_TIMEOUT_MS = 15_000;

export interface User {
  id: string;
  email: string;
  created_at: string;
  updated_at: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: getToken(),
  isAuthenticated: !!getToken(),
  isLoading: false,
  error: null,

  clearError: () => set({ error: null }),

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const data = await apiFetch<TokenResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
      });
      
      setToken(data.access_token);
      // Fetch current user details
      const user = await apiFetch<User>('/auth/me', { signal: AbortSignal.timeout(AUTH_TIMEOUT_MS) });
      set({ user, token: data.access_token, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      setToken(null);
      set({ 
        user: null,
        error: err.message || 'Failed to sign in', 
        isLoading: false, 
        isAuthenticated: false,
        token: null 
      });
      throw err;
    }
  },

  register: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      await apiFetch<User>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
      });
      
      // Auto-login after registration
      await get().login(email, password);
    } catch (err: any) {
      set({ error: err.message || 'Failed to register account', isLoading: false });
      throw err;
    }
  },

  logout: () => {
    // Optionally call logout endpoint
    const token = getToken();
    if (token) {
      apiFetch('/auth/logout', { method: 'POST' }).catch(() => {});
    }
    setToken(null);
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },

  checkAuth: async () => {
    const token = getToken();
    if (!token) {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }

    set({ isLoading: true });
    try {
      const user = await apiFetch<User>('/auth/me', { signal: AbortSignal.timeout(AUTH_TIMEOUT_MS) });
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err) {
      setToken(null);
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
