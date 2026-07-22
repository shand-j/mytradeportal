import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuthStore } from '@/stores/authStore';

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#F8F7F4]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#E7E5E4] border-t-[#D4650A]" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
