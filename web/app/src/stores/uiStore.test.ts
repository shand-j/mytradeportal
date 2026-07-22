import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';

import { useUiStore } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => {
    act(() => {
      useUiStore.setState({
        sidebarCollapsed: false,
        notificationOpen: false,
        toasts: [],
        currentPageTitle: 'Dashboard',
      });
    });
  });

  it('toggles the sidebar collapsed state', () => {
    act(() => {
      useUiStore.getState().toggleSidebar();
    });
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);

    act(() => {
      useUiStore.getState().toggleSidebar();
    });
    expect(useUiStore.getState().sidebarCollapsed).toBe(false);
  });

  it('sets the sidebar collapsed state explicitly', () => {
    act(() => {
      useUiStore.getState().setSidebarCollapsed(true);
    });
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);
  });

  it('toggles the notification panel', () => {
    act(() => {
      useUiStore.getState().setNotificationOpen(true);
    });
    expect(useUiStore.getState().notificationOpen).toBe(true);

    act(() => {
      useUiStore.getState().setNotificationOpen(false);
    });
    expect(useUiStore.getState().notificationOpen).toBe(false);
  });

  it('adds and removes toasts', () => {
    act(() => {
      useUiStore.getState().addToast({
        type: 'success',
        title: 'Saved',
        message: 'Settings saved',
      });
    });

    const toasts = useUiStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].title).toBe('Saved');

    const id = toasts[0].id;
    act(() => {
      useUiStore.getState().removeToast(id);
    });

    expect(useUiStore.getState().toasts).toHaveLength(0);
  });

  it('sets the current page title', () => {
    act(() => {
      useUiStore.getState().setPageTitle('Quotes');
    });
    expect(useUiStore.getState().currentPageTitle).toBe('Quotes');
  });
});
