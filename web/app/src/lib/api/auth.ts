import type { User } from '@/types';
import { api } from './client';

export interface LoginCredentials {
  email: string;
  password: string;
  // Sent as tenant_slug (the API client decamelizes keys); lets login resolve
  // the tenant explicitly instead of relying on the Host subdomain.
  tenantSlug?: string;
}

export const authService = {
  login: (credentials: LoginCredentials) =>
    api.post<User>('/auth/login', credentials),

  logout: () => api.post<void>('/auth/logout'),

  me: () => api.get<User>('/auth/me'),
};
