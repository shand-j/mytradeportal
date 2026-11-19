import { create } from "zustand";

/** Calendar scope on multi-seat plans: "me" (my jobs) or "all" (the team). */
export type CalendarScope = "me" | "all";

type CalendarState = {
  /** Last chosen scope — remembered for the session; defaults to "me". */
  scope: CalendarScope;
  setScope: (scope: CalendarScope) => void;
};

export const useCalendarStore = create<CalendarState>((set) => ({
  scope: "me",
  setScope: (scope) => set({ scope }),
}));
