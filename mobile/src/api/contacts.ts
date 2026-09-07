import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

/** Contact as returned by GET /contacts (camelized ContactRead). */
export type Contact = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  postcode: string | null;
  notes: string | null;
  createdAt: string;
};

/** List the tenant's contacts (trade users). */
export async function fetchContacts(): Promise<Contact[]> {
  return api.get<Contact[]>("/contacts");
}

export type CreateContactInput = {
  name: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  postcode?: string | null;
  notes?: string | null;
};

/** Create a contact for the current tenant (POST /contacts). */
export async function createContact(input: CreateContactInput): Promise<Contact> {
  return api.post<Contact>("/contacts", input);
}

/**
 * Reuse an existing contact that matches on phone (digits only) or exact name,
 * otherwise create a new one. Keeps manual lead entry from duplicating the CRM.
 */
export async function findOrCreateContact(input: CreateContactInput): Promise<Contact> {
  const digits = (value?: string | null) => (value ?? "").replace(/\D/g, "");
  const contacts = await fetchContacts();
  const match = contacts.find(
    (c) =>
      (digits(input.phone) !== "" && digits(c.phone) === digits(input.phone)) ||
      c.name.trim().toLowerCase() === input.name.trim().toLowerCase()
  );
  if (match) return match;
  return createContact(input);
}

/** Trade contacts list from the backend CRM. */
export function useContactsList() {
  const query = useQuery({
    queryKey: ["contacts"],
    queryFn: fetchContacts,
  });

  return {
    contacts: query.data ?? [],
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
    error: query.error,
  };
}
