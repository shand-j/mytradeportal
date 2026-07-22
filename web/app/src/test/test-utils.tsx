import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, type RenderOptions } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';

import { AuthProvider } from '@/lib/auth/AuthProvider';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });
}

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>{children}</AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, { wrapper: Providers, ...options });
}

export function renderPage(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  function PageWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: PageWrapper, ...options });
}

interface HookProviderOptions {
  queryClient?: QueryClient;
  initialEntries?: string[];
  withAuth?: boolean;
}

export function renderHookWithProviders<TResult, THookProps>(
  hook: (props: THookProps) => TResult,
  options: HookProviderOptions = {},
) {
  const { queryClient = createTestQueryClient(), initialEntries, withAuth = true } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    let inner = withAuth ? <AuthProvider>{children}</AuthProvider> : children;
    if (initialEntries) {
      inner = <MemoryRouter initialEntries={initialEntries}>{inner}</MemoryRouter>;
    }
    return <QueryClientProvider client={queryClient}>{inner}</QueryClientProvider>;
  }

  return renderHook(hook, { wrapper: Wrapper });
}

export function resetStores() {
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
  });
  useUiStore.setState({
    sidebarCollapsed: false,
    notificationOpen: false,
    toasts: [],
    currentPageTitle: 'Dashboard',
  });
}
