import { useEffect } from 'react';

import { authService } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setLoading, logout } = useAuthStore();

  useEffect(() => {
    let cancelled = false;

    authService
      .me()
      .then((user) => {
        if (!cancelled) setUser(user);
      })
      .catch(() => {
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [setUser, logout, setLoading]);

  return <>{children}</>;
}
