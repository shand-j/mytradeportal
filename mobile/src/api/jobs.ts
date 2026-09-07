import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { ApiContact } from "./quotes";
import { Job, JobStatus } from "../types";

/** Full backend job shape (camelized JobRead). */
export type ApiJob = {
  id: string;
  quoteId: string | null;
  title: string;
  description: string | null;
  status: string;
  scheduledStart: string | null;
  scheduledEnd: string | null;
  completedAt: string | null;
  notes: string | null;
  customer: ApiContact;
};

export async function fetchJobs(): Promise<ApiJob[]> {
  return api.get<ApiJob[]>("/jobs");
}

export async function fetchJob(id: string): Promise<ApiJob> {
  return api.get<ApiJob>(`/jobs/${id}`);
}

export async function startJob(id: string): Promise<ApiJob> {
  return api.post<ApiJob>(`/jobs/${id}/start`);
}

export async function completeJob(id: string): Promise<ApiJob> {
  return api.post<ApiJob>(`/jobs/${id}/complete`);
}

/** Backend default is "scheduled"; the app's UI vocabulary uses "confirmed". */
const STATUS_MAP: Record<string, JobStatus> = {
  scheduled: "confirmed",
  confirmed: "confirmed",
  in_progress: "in_progress",
  completed: "completed",
  cancelled: "cancelled",
};

/** Local (not UTC) calendar date, so jobs bucket into the day the user sees. */
function toLocalIsoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Map a backend job into the app's display `Job` shape. */
function mapJob(j: ApiJob): Job {
  const start = j.scheduledStart ? new Date(j.scheduledStart) : null;
  const end = j.scheduledEnd ? new Date(j.scheduledEnd) : null;
  const formatTime = (d: Date) =>
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return {
    id: j.id,
    quoteId: j.quoteId ?? "",
    title: j.title,
    customerName: j.customer?.name ?? "Customer",
    postcode: j.customer?.postcode ?? "",
    address: j.customer?.address ?? "",
    status: STATUS_MAP[j.status] ?? "confirmed",
    assignedTo: "",
    date: start ? toLocalIsoDate(start) : "",
    time: start ? formatTime(start) : "",
    endTime: end ? formatTime(end) : undefined,
    phone: j.customer?.phone ?? "",
  };
}

/** Jobs list for the Calendar/Dashboard. Returns backend jobs mapped into the app's `Job` shape. */
export function useJobsList() {
  const query = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
  });

  return {
    jobs: (query.data ?? []).map(mapJob),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/**
 * A single job by id. Returns both the mapped app `Job` (for display) and the
 * raw `ApiJob` (for the contact id needed when creating an invoice from the job).
 */
export function useJobDetail(id: string | undefined) {
  const query = useQuery({
    queryKey: ["job", id],
    queryFn: () => fetchJob(id as string),
    enabled: !!id,
  });

  return {
    job: query.data ? mapJob(query.data) : undefined,
    raw: query.data,
    isConnected: query.isSuccess,
    isLoading: !!id && query.isLoading,
  };
}

/** Mutations for the job lifecycle, invalidating the jobs caches on success. */
export function useJobActions(id: string | undefined) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["jobs"] });
    qc.invalidateQueries({ queryKey: ["job", id] });
  };
  const start = useMutation({ mutationFn: () => startJob(id as string), onSuccess: invalidate });
  const complete = useMutation({
    mutationFn: () => completeJob(id as string),
    onSuccess: invalidate,
  });
  return { start, complete };
}
