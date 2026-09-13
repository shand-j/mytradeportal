import { createContext, useContext } from 'react'
import type { PortalConfig } from './api'

export interface PortalContextValue {
  slug: string
  config: PortalConfig
  sessionExpired: boolean
  dismissSessionExpired: () => void
  /** Bumped whenever the session is invalidated so auth-gated views re-render. */
  sessionVersion: number
}

export const PortalContext = createContext<PortalContextValue | null>(null)

export function usePortal(): PortalContextValue {
  const ctx = useContext(PortalContext)
  if (!ctx) throw new Error('usePortal must be used inside PortalProvider')
  return ctx
}
