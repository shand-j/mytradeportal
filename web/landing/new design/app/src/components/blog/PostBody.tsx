import { Fragment } from 'react'
import type { Block } from '@/content/blog/posts'

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

/** Renders a post's structured blocks in the brutalist brand style. */
export function PostBody({ blocks }: { blocks: Block[] }) {
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
          case 'quote':
            return (
              <blockquote
                key={i}
                className="my-[var(--space-lg)] border-y-2 border-[var(--ink)] bg-[var(--paper-2)] px-[var(--space-lg)] py-[var(--space-lg)]"
              >
                <p className="font-display text-[clamp(1.1rem,1.6vw,1.35rem)] font-bold leading-[1.3] text-[var(--ink)]">
                  “<Inline text={block.text} />”
                </p>
                {block.cite && (
                  <cite className="mt-[var(--space-xs)] block font-mono text-[12px] uppercase not-italic tracking-[0.18em] text-[var(--muted)]">
                    {block.cite}
                  </cite>
                )}
              </blockquote>
            )
        }
      })}
    </div>
  )
}
