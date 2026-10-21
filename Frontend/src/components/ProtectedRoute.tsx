import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';

interface ProtectedRouteProps {
  children?: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-void-black text-starlight-white">
        <div className="w-12 h-12 rounded-full border border-copper-glow/40 border-t-copper-glow animate-spin mb-4"></div>
        <p className="font-label-sm text-xs text-on-surface-variant/70 uppercase tracking-widest">
          Authenticating Archives...
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/signin" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};

export const PublicOnlyRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading && isAuthenticated) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-void-black text-starlight-white">
        <div className="w-12 h-12 rounded-full border border-copper-glow/40 border-t-copper-glow animate-spin mb-4"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/worlds" replace />;
  }

  return <>{children}</>;
};
