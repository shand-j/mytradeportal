import { create } from "zustand";

export type SyncItemKind = "quote" | "certificate" | "invoice" | "photo" | "job";

export type SyncItem = {
  id: string;
  kind: SyncItemKind;
  label: string;
  createdAt: number;
  status: "pending" | "synced";
};

type OfflineState = {
  isOnline: boolean;
  syncing: boolean;
  /** Briefly true right after a sync completes, to show an "all synced" flash. */
  justSynced: boolean;
  queue: SyncItem[];
  pendingCount: () => number;
  setOnline: (online: boolean) => void;
  toggleOnline: () => void;
  /** Queue a change. Returns whether it was stored offline (true) or synced live. */
  enqueue: (kind: SyncItemKind, label: string) => boolean;
  sync: () => void;
  reset: () => void;
};

let syncTimer: ReturnType<typeof setTimeout> | null = null;

export const useOfflineStore = create<OfflineState>((set, get) => ({
  isOnline: true,
  syncing: false,
  justSynced: false,
  queue: [],

  pendingCount: () => get().queue.filter((i) => i.status === "pending").length,

  setOnline: (online) => {
    set({ isOnline: online });
    // Coming back online with a backlog kicks off a sync automatically.
    if (online && get().queue.some((i) => i.status === "pending")) {
      get().sync();
    }
  },

  toggleOnline: () => get().setOnline(!get().isOnline),

  enqueue: (kind, label) => {
    const offline = !get().isOnline;
    const item: SyncItem = {
      id: `${kind}-${Date.now()}`,
      kind,
      label,
      createdAt: Date.now(),
      status: offline ? "pending" : "synced",
    };
    set((s) => ({ queue: [item, ...s.queue].slice(0, 25) }));
    return offline;
  },

  sync: () => {
    if (get().syncing) return;
    const hasPending = get().queue.some((i) => i.status === "pending");
    if (!hasPending) return;
    set({ syncing: true, justSynced: false });
    if (syncTimer) clearTimeout(syncTimer);
    // Simulate uploading the queued changes.
    syncTimer = setTimeout(() => {
      set((s) => ({
        syncing: false,
        justSynced: true,
        queue: s.queue.map((i) => ({ ...i, status: "synced" as const })),
      }));
      syncTimer = setTimeout(() => set({ justSynced: false }), 2600);
    }, 2200);
  },

  reset: () => set({ isOnline: true, syncing: false, justSynced: false, queue: [] }),
}));
