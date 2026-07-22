import { create } from 'zustand';
import type { Toast } from '@/types';

interface UiState {
  sidebarCollapsed: boolean;
  notificationOpen: boolean;
  toasts: Toast[];
  currentPageTitle: string;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setNotificationOpen: (open: boolean) => void;
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  setPageTitle: (title: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  notificationOpen: false,
  toasts: [],
  currentPageTitle: 'Dashboard',
  toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setNotificationOpen: (open) => set({ notificationOpen: open }),
  addToast: (toast) => set(s => ({
    toasts: [...s.toasts, { ...toast, id: Math.random().toString(36).slice(2) }],
  })),
  removeToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
  setPageTitle: (title) => set({ currentPageTitle: title }),
}));
