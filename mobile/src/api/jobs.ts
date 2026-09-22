import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/apiClient";
import { ApiContact } from "./quotes";
import { Job, JobStatus } from "../types";

/** One structured measurement recorded against a job. */
export type MeasurementEntry = { label: string; value: string };

/** Before/after/general label on a job photo (backend MediaAsset.kind). */
export type JobPhotoKind = "before" | "after" | "general";

/** A job photo asset as surfaced on JobRead.media_assets (camelized). */
export type ApiJobMediaAsset = {
  id: string;
  fileUrl: string;
  fileKey: string | null;
  mimeType: string | null;
  kind: JobPhotoKind;
};

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
  /** Structured measurements recorded for the job (label + value pairs). */
  measurements: MeasurementEntry[];
  assignedUserId: string | null;
  /** Display name of the assignee, derived server-side. */
  assignedTo: string | null;
  /** Photo URLs carried over from the source quote. */
  photos: string[];
  /** Same photos with their before/after/general label. */
  mediaAssets?: ApiJobMediaAsset[];
  customer: ApiContact;
};

export async function fetchJobs(assignedUserId?: string): Promise<ApiJob[]> {
  const query = assignedUserId ? `?assigned_user_id=${assignedUserId}` : "";
  return api.get<ApiJob[]>(`/jobs${query}`);
}

export async function fetchJob(id: string): Promise<ApiJob> {
  return api.get<ApiJob>(`/jobs/${id}`);
}

export type CreateJobInput = {
  contactId: string;
  quoteId?: string;
  title: string;
  description?: string;
  /** ISO datetimes; snakeized to scheduled_start/scheduled_end on the wire. */
  scheduledStart?: string;
  scheduledEnd?: string;
  notes?: string;
  measurements?: MeasurementEntry[];
  assignedUserId?: string;
};

/** Create a standalone job (POST /jobs). */
export async function createJob(input: CreateJobInput): Promise<ApiJob> {
  return api.post<ApiJob>("/jobs", input);
}

export type UpdateJobInput = {
  scheduledStart?: string;
  scheduledEnd?: string;
  notes?: string;
  /** Replaces the job's measurements list (send [] to clear). */
  measurements?: MeasurementEntry[];
  /** Pass null to unassign. */
  assignedUserId?: string | null;
};

/** Update a job's schedule, notes or assignee (PATCH /jobs/{id}). */
export async function updateJob(id: string, input: UpdateJobInput): Promise<ApiJob> {
  return api.patch<ApiJob>(`/jobs/${id}`, input);
}

export type ConvertToJobSchedule = {
  scheduledStart?: string;
  scheduledEnd?: string;
  notes?: string;
  /** Structured measurements carried onto the converted job. */
  measurements?: MeasurementEntry[];
  assignedUserId?: string;
};

/**
 * Convert an approved quote into a job (POST /quotes/{id}/convert-to-job).
 * Throws ApiError(409) when the quote already has a job.
 */
export async function convertQuoteToJob(
  quoteId: string,
  schedule?: ConvertToJobSchedule
): Promise<ApiJob> {
  return api.post<ApiJob>(`/quotes/${quoteId}/convert-to-job`, schedule ?? {});
}

/** Camelized ScheduleSuggestion from GET /jobs/suggest-schedule. */
export type ScheduleSuggestion = {
  startDate: string;
  startTime: string;
  days: { date: string; hours: number }[];
  isMultiDay: boolean;
};

/**
 * Earliest start where the quote's full working-day block sequence fits
 * (GET /jobs/suggest-schedule?quote_id=). Null when nothing fits within the
 * server's search window (404).
 */
export async function fetchScheduleSuggestion(quoteId: string): Promise<ScheduleSuggestion | null> {
  try {
    return await api.get<ScheduleSuggestion>(`/jobs/suggest-schedule?quote_id=${quoteId}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/** Schedule suggestion for a quote; disabled until a quote is selected. */
export function useScheduleSuggestion(quoteId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["schedule-suggestion", quoteId],
    queryFn: () => fetchScheduleSuggestion(quoteId as string),
    enabled: !!quoteId,
  });

  return {
    suggestion: query.data ?? null,
    isConnected: query.isSuccess,
    isLoading: !!quoteId && query.isLoading,
  };
}

export async function startJob(id: string): Promise<ApiJob> {
  return api.post<ApiJob>(`/jobs/${id}/start`);
}

export type AttachJobMediaInput = {
  fileUrl: string;
  fileKey?: string | null;
  mimeType?: string | null;
  sizeBytes?: number | null;
  kind: JobPhotoKind;
};

/** Attach an uploaded photo to a job with its before/after/general label. */
export async function attachJobMedia(jobId: string, input: AttachJobMediaInput): Promise<ApiJob> {
  return api.post<ApiJob>(`/jobs/${jobId}/media`, input);
}

/** Relabel a job photo (PATCH /jobs/{id}/media/{assetId}). */
export async function updateJobMediaKind(
  jobId: string,
  assetId: string,
  kind: JobPhotoKind
): Promise<ApiJob> {
  return api.patch<ApiJob>(`/jobs/${jobId}/media/${assetId}`, { kind });
}

export async function completeJob(id: string): Promise<ApiJob> {
  return api.post<ApiJob>(`/jobs/${id}/complete`);
}

/** Backend default is "scheduled"; the app's UI vocabulary uses "confirmed". */
const STATUS_MAP: Record<string, JobStatus> = {
  draft: "draft",
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
    assignedTo: j.assignedTo ?? "",
    date: start ? toLocalIsoDate(start) : "",
    time: start ? formatTime(start) : "",
    endTime: end ? formatTime(end) : undefined,
    phone: j.customer?.phone ?? "",
  };
}

/** Jobs list for the Calendar/Dashboard. Returns backend jobs mapped into the app's `Job` shape. */
export function useJobsList(filter?: { assignedUserId?: string | null }) {
  const assignedUserId = filter?.assignedUserId ?? undefined;
  const query = useQuery({
    queryKey: ["jobs", assignedUserId ?? "all"],
    queryFn: () => fetchJobs(assignedUserId),
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

/** Mutation: create a standalone job and refresh the jobs caches. */
export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job", job.id] });
    },
  });
}

/** Mutation: update a job's schedule/notes/assignee and refresh the caches. */
export function useUpdateJob(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateJobInput) => updateJob(id as string, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job", id] });
      // Schedule changes alter free-slot availability for that day.
      qc.invalidateQueries({ queryKey: ["availability"] });
    },
  });
}

/** Mutation: convert an approved quote into a job and refresh jobs/quotes caches. */
export function useConvertQuoteToJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      quoteId,
      schedule,
    }: {
      quoteId: string;
      schedule?: ConvertToJobSchedule;
    }) => convertQuoteToJob(quoteId, schedule),
    onSuccess: (_job, { quoteId }) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["quote", quoteId] });
    },
  });
}
