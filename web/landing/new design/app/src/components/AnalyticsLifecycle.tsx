import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router'
import { startBrowserAnalytics, trackScreen } from '../lib/analytics'

export function AnalyticsLifecycle() {
  const location = useLocation()
  const previousPath = useRef<string | null>(null)

  useEffect(() => startBrowserAnalytics(), [])

  useEffect(() => {
    trackScreen(location.pathname, previousPath.current ?? undefined)
    previousPath.current = location.pathname
  }, [location.pathname])

  return null
}
