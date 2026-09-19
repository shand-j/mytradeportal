import { create } from "zustand";
import type { Contact } from "../api/contacts";

/**
 * Hands a freshly created CRM customer back to the quote intake screen.
 * The intake pushes the Add New Customer form on top of itself; on save the
 * form stashes the contact here and pops back, so the intake keeps its
 * in-progress form state and pre-selects the new customer.
 */
type IntakeCustomerState = {
  pending: Contact | null;
  setPending: (contact: Contact) => void;
  clear: () => void;
};

export const useIntakeCustomerStore = create<IntakeCustomerState>((set) => ({
  pending: null,
  setPending: (contact) => set({ pending: contact }),
  clear: () => set({ pending: null }),
}));
