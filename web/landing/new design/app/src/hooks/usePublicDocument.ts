import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import {
  fetchPublicDocument,
  PublicDocsApiError,
  type PublicDocPayload,
} from '../lib/public-docs-api'

type Status = 'loading' | 'invalid' | 'error' | 'loaded'

export function useNoIndex(): void {
  useEffect(() => {
    let meta = document.querySelector<HTMLMetaElement>('meta[name="robots"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'robots'
      document.head.appendChild(meta)
    }
    meta.content = 'noindex, nofollow'
  }, [])
}

export function usePublicDocument(kind: 'quote' | 'invoice') {
  const { token = '' } = useParams()
  const [status, setStatus] = useState<Status>(token ? 'loading' : 'invalid')
  const [error, setError] = useState('')
  const [doc, setDoc] = useState<PublicDocPayload | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchPublicDocument(kind, token)
      .then((payload) => {
        if (cancelled) return
        setDoc(payload)
        setStatus('loaded')
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof PublicDocsApiError && err.status === 404) {
          setStatus('invalid')
        } else {
          setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
          setStatus('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [kind, token])

  return { status, error, doc, setDoc }
}
