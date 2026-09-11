import { useEffect } from 'react'

/**
 * Sets document.title and the meta[name="description"] tag for the current
 * page. Restores nothing on unmount — every routed page sets its own.
 */
export function usePageMeta(title: string, description: string) {
  useEffect(() => {
    document.title = title

    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'description'
      document.head.appendChild(meta)
    }
    meta.content = description
  }, [title, description])
}
