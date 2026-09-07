import { create } from "zustand";

/**
 * Tracks an in-flight async quote generation (POST /quotes/generate-async).
 * The intake screen kicks the job off and navigates away; the quotes/leads
 * list shows a persistent banner until the backend's quote_ready notification
 * arrives (polled by `useQuoteReadyWatcher`).
 */
export type QuoteGenerationPhase = "generating" | "ready" | "failed";

type QuoteGenerationState = {
  phase: QuoteGenerationPhase | null;
  /** Quote id parsed from the quote_ready notification link, when known. */
  readyQuoteId: string | null;
  /** The tradesperson dismissed the banner for the current generation. */
  dismissed: boolean;
  start: () => void;
  markReady: (quoteId: string | null) => void;
  markFailed: () => void;
  dismiss: () => void;
  reset: () => void;
};

export const useQuoteGenerationStore = create<QuoteGenerationState>((set) => ({
  phase: null,
  readyQuoteId: null,
  dismissed: false,

  start: () => set({ phase: "generating", readyQuoteId: null, dismissed: false }),
  markReady: (quoteId) => set({ phase: "ready", readyQuoteId: quoteId, dismissed: false }),
  markFailed: () => set({ phase: "failed", readyQuoteId: null, dismissed: false }),
  dismiss: () => set({ dismissed: true }),
  reset: () => set({ phase: null, readyQuoteId: null, dismissed: false }),
}));
