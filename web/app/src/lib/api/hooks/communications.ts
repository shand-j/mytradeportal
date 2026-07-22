import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Communication, CommunicationChannel } from '@/types';

const communicationKeys = {
  all: ['communications'] as const,
};

export function useCommunications() {
  return useQuery<Communication[], ApiError>({
    queryKey: communicationKeys.all,
    queryFn: () => api.get('/communications'),
  });
}

export interface CreateCommunicationPayload {
  contactId: string;
  channel: CommunicationChannel;
  content: string;
  direction?: Communication['direction'];
}

export function useCreateCommunication() {
  const queryClient = useQueryClient();

  return useMutation<Communication, ApiError, CreateCommunicationPayload>({
    mutationFn: (data) => api.post('/communications', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communicationKeys.all });
    },
  });
}
