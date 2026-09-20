import { Fragment } from 'react'
import type { HelpBlock } from '@/content/help/articles'

/** Renders `**bold**` inline markers as <strong>. */
function Inline({ text }: { text: string }) {
  const segments = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
  return (
    <>
      {segments.map((s, i) =>
        s.startsWith('**') ? (
          <strong key={i} className="font-semibold text-[var(--ink)]">
            {s.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={i}>{s}</Fragment>
        ),
      )}
    </>
  )
}

/**
 * Renders a help article's structured blocks in the brutalist brand style
 * (mirrors components/blog/PostBody, plus ordered lists and screenshot
 * placeholders).
 */
export function HelpBody({ blocks }: { blocks: HelpBlock[] }) {
  return (
    <div className="space-y-[var(--space-md)]">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'h2':
            return (
              <h2
                key={i}
                className="!mt-[var(--space-xl)] flex items-baseline gap-[var(--space-sm)] font-display text-[clamp(1.25rem,2vw,1.6rem)] font-extrabold uppercase leading-[1.1] tracking-[-0.01em] text-[var(--ink)]"
              >
                <span aria-hidden className="inline-block h-[0.6em] w-[0.6em] shrink-0 translate-y-[0.05em] bg-[var(--accent)]" />
                {block.text}
              </h2>
            )
          case 'p':
            return (
              <p key={i} className="max-w-[68ch] text-[16px] leading-[1.8] text-[var(--muted)]">
                <Inline text={block.text} />
              </p>
            )
          case 'ul':
            return (
              <ul key={i} className="max-w-[68ch] space-y-[var(--space-xs)] border-l-2 border-[var(--accent)] pl-[var(--space-lg)]">
                {block.items.map((item, j) => (
                  <li key={j} className="text-[15.5px] leading-[1.7] text-[var(--muted)]">
                    <Inline text={item} />
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={i} className="max-w-[68ch] space-y-[var(--space-xs)] border-l-2 border-[var(--accent)] pl-[var(--space-lg)] [counter-reset:step]">
                {block.items.map((item, j) => (
                  <li
                    key={j}
                    className="text-[15.5px] leading-[1.7] text-[var(--muted)] [counter-increment:step] before:mr-[var(--space-xs)] before:font-mono before:text-[13px] before:font-medium before:text-[var(--accent-dark)] before:content-[counter(step)_'.']"
                  >
                    <Inline text={item} />
                  </li>
                ))}
              </ol>
            )
          case 'shot':
            // Placeholder frame: real screenshots are captured later via
            // scripts/capture-screenshots.mjs and swapped in for these.
            return (
              <div
                key={i}
                aria-hidden
                className="my-[var(--space-lg)] flex max-w-[560px] items-center justify-center border-2 border-dashed border-[var(--ink)]/40 bg-[var(--paper-2)] px-[var(--space-lg)] py-[var(--space-2xl)]"
              >
                <p className="text-center font-mono text-[11.5px] uppercase tracking-[0.16em] text-[var(--muted)]">
                  Screenshot to come
                  <span className="mt-[var(--space-2xs)] block normal-case tracking-normal">
                    {block.label}
                  </span>
                </p>
              </div>
            )
        }
      })}
    </div>
  )
}
