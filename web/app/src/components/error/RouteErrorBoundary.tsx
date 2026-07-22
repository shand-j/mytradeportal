import type { ReactNode } from 'react';
import { ErrorBoundary } from './ErrorBoundary';

interface RouteErrorBoundaryProps {
  children: ReactNode;
}

/**
 * Thin wrapper around ErrorBoundary for use at the route level.
 * Catches render errors in page components so a single bad page cannot bring
 * down the whole shell.
 */
export function RouteErrorBoundary({ children }: RouteErrorBoundaryProps) {
  return <ErrorBoundary>{children}</ErrorBoundary>;
}
