import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../lib/apiClient";

/** Contact as returned by GET /contacts (camelized ContactRead). */
export type Contact = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  postcode: string | null;
  notes: string | null;
  preferredContactMethod: string | null;
  propertyType: string | null;
  bedrooms: number | null;
  parkingNotes: string | null;
  accessNotes: string | null;
  hasAccount: boolean;
  createdAt: string;
};

/** List the tenant's contacts (trade users). */
export async function fetchContacts(): Promise<Contact[]> {
  return api.get<Contact[]>("/contacts");
}

/** A single contact by id (GET /contacts/{id}). */
export async function fetchContact(id: string): Promise<Contact> {
  return api.get<Contact>(`/contacts/${id}`);
}

export function useContact(id: string | undefined) {
  const query = useQuery({
    queryKey: ["contact", id],
    queryFn: () => fetchContact(id as string),
    enabled: !!id,
  });
  return {
    contact: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
}

export type CreateContactInput = {
  name: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  postcode?: string | null;
  notes?: string | null;
  preferredContactMethod?: string | null;
  propertyType?: string | null;
  bedrooms?: number | null;
  parkingNotes?: string | null;
  accessNotes?: string | null;
};

export type UpdateContactInput = Partial<CreateContactInput>;

/** Create a contact for the current tenant (POST /contacts). */
export async function createContact(input: CreateContactInput): Promise<Contact> {
  return api.post<Contact>("/contacts", input);
}

/** Update editable CRM fields on a contact (PATCH /contacts/{id}). */
export async function updateContact(id: string, input: UpdateContactInput): Promise<Contact> {
  return api.patch<Contact>(`/contacts/${id}`, input);
}

const digits = (value?: string | null) => (value ?? "").replace(/\D/g, "");
const normaliseName = (value?: string | null) => (value ?? "").trim().replace(/\s+/g, " ").toLowerCase();
const normaliseEmail = (value?: string | null) => (value ?? "").trim().toLowerCase();

/** Client-side mirror of the backend dedupe rule (C15). */
export function findDuplicateContact(contacts: Contact[], input: CreateContactInput): Contact | undefined {
  const email = normaliseEmail(input.email);
  const name = normaliseName(input.name);
  const phone = digits(input.phone);
  return contacts.find(
    (c) =>
      (email !== "" && normaliseEmail(c.email) === email) ||
      (phone !== "" && digits(c.phone) === phone && normaliseName(c.name) === name)
  );
}

/**
 * Reuse an existing contact that matches on email, phone+name, or exact name,
 * otherwise create a new one. Keeps manual lead entry from duplicating the CRM.
 * Falls back to the server-side duplicate when the backend rejects with 409.
 */
export async function findOrCreateContact(input: CreateContactInput): Promise<Contact> {
  const contacts = await fetchContacts();
  const match =
    findDuplicateContact(contacts, input) ??
    contacts.find((c) => normaliseName(c.name) === normaliseName(input.name));
  if (match) return match;
  try {
    return await createContact(input);
  } catch (err) {
    // Backend dedupe guard (409 duplicate_contact:…): re-resolve and reuse.
    if (err instanceof ApiError && err.status === 409) {
      const fresh = await fetchContacts();
      const serverMatch = findDuplicateContact(fresh, input);
      if (serverMatch) return serverMatch;
    }
    throw err;
  }
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
