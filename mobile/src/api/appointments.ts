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
