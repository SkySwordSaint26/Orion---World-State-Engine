const API_BASE_URL = import.meta.env.DEV ? '/api/v1' : import.meta.env.VITE_API_BASE_URL || '/api/v1';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export function getToken(): string | null {
  return localStorage.getItem('orion_token');
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem('orion_token', token);
  } else {
    localStorage.removeItem('orion_token');
  }
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  
  // Format endpoint path
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${API_BASE_URL}${path}`;

  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'TimeoutError') {
      throw new ApiError('The Orion backend did not respond in time. Please try again.', 0);
    }
    if (error instanceof TypeError) {
      throw new ApiError('Cannot reach the Orion backend. Check that it is running, then try again.', 0);
    }
    throw error;
  }

  if (response.status === 401) {
    setToken(null);
  }

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    let errorData = null;
    try {
      errorData = await response.json();
      if (errorData.detail) {
        errorDetail = typeof errorData.detail === 'string' 
          ? errorData.detail 
          : JSON.stringify(errorData.detail);
      }
    } catch (_) {
      // Ignore JSON parse errors for non-JSON responses
    }
    throw new ApiError(errorDetail, response.status, errorData);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}
