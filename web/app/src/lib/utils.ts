import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format a GBP amount with exactly 2 decimal places (£976.80, not £976.8). */
export function formatGBP(value: number): string {
  return `£${value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function displayInitials(displayName: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean)
  const firstGrapheme = (word: string) => {
    if (typeof Intl !== 'undefined' && 'Segmenter' in Intl) {
      const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' })
      return segmenter.segment(word)[Symbol.iterator]().next().value?.segment ?? Array.from(word)[0] ?? ''
    }
    return Array.from(word)[0] ?? ''
  }
  return words.slice(0, 2).map(firstGrapheme).join('')
}
