import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

/** Camelized AppointmentRead (subset the app uses). */
export type ApiAppointment = {
  id: string;
  title: string;
  startAt: string;
  endAt: string;
  status: string;
  address: string | null;
  notes: string | null;
};

/** App-facing appointment shape. */
export type Appointment = {
  id: string;
  title: string;
  date: string;
  time: string;
  address: string;
  status: "confirmed" | "cancelled" | "completed" | "no_show";
};

const STATUS_MAP: Record<string, Appointment["status"]> = {
  confirmed: "confirmed",
  cancelled: "cancelled",
  completed: "completed",
  no_show: "no_show",
};

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function mapAppointment(a: ApiAppointment): Appointment {
  const start = new Date(a.startAt);
  const end = new Date(a.endAt);
  return {
    id: a.id,
    title: a.title,
    date: start.toLocaleDateString(),
    time: `${formatTime(start)} – ${formatTime(end)}`,
    address: a.address ?? "",
    status: STATUS_MAP[a.status] ?? "confirmed",
  };
}

export async function fetchMyAppointments(): Promise<ApiAppointment[]> {
  return api.get<ApiAppointment[]>("/customer/appointments");
}

export async function fetchAppointments(assignedUserId?: string): Promise<ApiAppointment[]> {
  const query = assignedUserId ? `?assigned_user_id=${assignedUserId}` : "";
  return api.get<ApiAppointment[]>(`/appointments${query}`);
}

/** Appointment reduced to what the trade calendar needs to bucket it by day. */
export type CalendarAppointment = {
  id: string;
  /** Local "YYYY-MM-DD" date, so entries bucket into the day the user sees. */
  date: string;
};

/** Local (not UTC) calendar date — same rule as jobs (see api/jobs.ts). */
function toLocalIsoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Tenant appointments for the trade calendar (GET /appointments). Mirrors the
 * availability rules: cancelled and no-show appointments never block the
 * calendar, so they are dropped from the list. `assignedUserId` powers the
 * multi-seat All/Me filter, like `useJobsList`.
 */
export function useAppointmentsList(filter?: { assignedUserId?: string | null }) {
  const assignedUserId = filter?.assignedUserId ?? undefined;
  const query = useQuery({
    queryKey: ["appointments", assignedUserId ?? "all"],
    queryFn: () => fetchAppointments(assignedUserId),
  });

  return {
    appointments: (query.data ?? [])
      .filter((a) => a.status !== "cancelled" && a.status !== "no_show")
      .map((a): CalendarAppointment => ({ id: a.id, date: toLocalIsoDate(new Date(a.startAt)) })),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/**
 * Free 1-hour start slots (ISO datetimes) for a trade calendar date
 * (GET /appointments/availability?date=YYYY-MM-DD). Appointments and scheduled
 * jobs both block a slot.
 */
export async function fetchAvailability(date: string): Promise<string[]> {
  return api.get<string[]>(`/appointments/availability?date=${date}`);
}

/** Suggested free slots for a date; disabled until a date is chosen. */
export function useAvailability(date: string | null) {
  const query = useQuery({
    queryKey: ["availability", date],
    queryFn: () => fetchAvailability(date as string),
    enabled: !!date,
  });

  return {
    slots: query.data ?? [],
    isConnected: query.isSuccess,
    isLoading: !!date && query.isLoading,
  };
}

export async function createCustomerAppointment(input: {
  title: string;
  startAt: string;
  endAt: string;
  address?: string;
  notes?: string;
}): Promise<ApiAppointment> {
  return api.post<ApiAppointment>("/customer/appointments", {
    title: input.title,
    startAt: input.startAt,
    endAt: input.endAt,
    address: input.address,
    notes: input.notes,
  });
}

/** The logged-in customer's appointments. Returns mapped appointments from the backend. */
export function useMyAppointments() {
  const query = useQuery({
    queryKey: ["my-appointments"],
    queryFn: fetchMyAppointments,
  });

  return {
    appointments: (query.data ?? []).map(mapAppointment),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** Mutation: create a customer appointment and refresh the appointments cache. */
export function useCreateCustomerAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      title: string;
      startAt: string;
      endAt: string;
      address?: string;
      notes?: string;
    }) => createCustomerAppointment(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-appointments"] });
    },
  });
}
