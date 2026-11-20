import { useEffect, useState } from 'react'

const API: string = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_DEMO_API_URL ?? ''

type FeatureFlagsResponse = {
  paddle_billing?: boolean
}

type FeatureFlags = {
  paddleBilling: boolean
}

const DEFAULT_FLAGS: FeatureFlags = {
  paddleBilling: false,
}

export function useFeatureFlags() {
  const [flags, setFlags] = useState<FeatureFlags>(DEFAULT_FLAGS)

  useEffect(() => {
    let cancelled = false
    if (!API) return
    fetch(`${API}/feature-flags`)
      .then(async (res) => {
        if (!res.ok) return
        const body = (await res.json()) as FeatureFlagsResponse
        if (!cancelled) {
          setFlags({ paddleBilling: body.paddle_billing === true })
        }
      })
      .catch(() => {
        if (!cancelled) setFlags(DEFAULT_FLAGS)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return flags
}
