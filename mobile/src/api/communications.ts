import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AI_TIMEOUT_MS, api } from "../lib/apiClient";

export type ChatSenderRole = "customer" | "business" | "ai";

export type AiMetadata = {
  complete?: boolean;
  confidence?: number;
  /** Quick-reply choices for the customer, rendered as tappable chips. */
  options?: string[];
  /** AI-recommended questions for the electrician's call with the customer. */
  suggestedQuestions?: string[];
  [key: string]: unknown;
};

export type ChatMessage = {
  id: string;
  quoteRequestId: string | null;
  senderRole: ChatSenderRole;
  body: string;
  createdAt: string;
  aiMetadata?: AiMetadata | null;
};

type CommunicationRead = {
  id: string;
  tenantId: string;
  contactId: string | null;
  quoteRequestId: string | null;
  channel: string;
  direction: string;
  senderRole: ChatSenderRole;
  subject: string | null;
  body: string | null;
  status: string;
  aiMetadata: AiMetadata | null;
  createdAt: string;
};

function mapCommunication(row: CommunicationRead): ChatMessage {
  return {
    id: row.id,
    quoteRequestId: row.quoteRequestId,
    senderRole: row.senderRole,
    body: row.body ?? "",
    createdAt: row.createdAt,
    aiMetadata: row.aiMetadata ?? null,
  };
}

/** Load the chat thread for a quote request from the backend. */
export async function fetchCommunications(
  quoteRequestId: string
): Promise<ChatMessage[]> {
  const rows = await api.get<CommunicationRead[]>(
    `/communications?quote_request_id=${encodeURIComponent(quoteRequestId)}`
  );
  return rows.map(mapCommunication);
}

export type CreateCommunicationInput = {
  quoteRequestId: string;
  body: string;
  senderRole: ChatSenderRole;
};

/**
 * Post a reply to the chat thread.
 *
 * The backend uses ``sender_role`` (customer | business | ai) to identify the
 * author; ``channel`` is always ``in_app_chat`` for mobile messages.
 */
export async function createCommunication(
  input: CreateCommunicationInput
): Promise<ChatMessage> {
  const row = await api.post<CommunicationRead>("/communications", {
    quoteRequestId: input.quoteRequestId,
    channel: "in_app_chat",
    senderRole: input.senderRole,
    body: input.body,
  });
  return mapCommunication(row);
}

/**
 * Ask the Kimi-backed AI for one clarifying question.
 *
 * The endpoint reads the quote request + prior messages, calls the LLM, and
 * persists the assistant message. The returned message is then shown in the
 * chat thread.
 */
export async function generateAiFollowup(
  quoteRequestId: string
): Promise<ChatMessage> {
  const row = await api.post<CommunicationRead>(
    `/communications/${encodeURIComponent(quoteRequestId)}/ai-followup`,
    {},
    { timeoutMs: AI_TIMEOUT_MS }
  );
  return mapCommunication(row);
}

export function useCommunications(
  quoteRequestId: string | undefined,
  senderRole: ChatSenderRole
) {
  const query = useQuery({
    queryKey: ["communications", quoteRequestId],
    queryFn: () => fetchCommunications(quoteRequestId as string),
    enabled: !!quoteRequestId,
  });

  const qc = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (body: string) =>
      createCommunication({ quoteRequestId: quoteRequestId as string, body, senderRole }),
    onSuccess: () => {
      if (quoteRequestId) {
        qc.invalidateQueries({ queryKey: ["communications", quoteRequestId] });
      }
    },
  });

  const followupMutation = useMutation({
    mutationFn: () => generateAiFollowup(quoteRequestId as string),
    onSuccess: () => {
      if (quoteRequestId) {
        qc.invalidateQueries({ queryKey: ["communications", quoteRequestId] });
      }
    },
  });

  return {
    messages: query.data ?? [],
    isConnected: query.isSuccess,
    isLoading: !!quoteRequestId && query.isLoading,
    error: query.error,
    sendMessage: createMutation.mutateAsync,
    isSending: createMutation.isPending,
    generateAiFollowup: followupMutation.mutateAsync,
    isGeneratingFollowup: followupMutation.isPending,
  };
}
