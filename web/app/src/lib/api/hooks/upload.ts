import { useMutation } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { PresignedUpload } from '@/types';

export interface UploadUrlVariables {
  filename: string;
  contentType: string;
}

export function useUploadUrl() {
  return useMutation<PresignedUpload, ApiError, UploadUrlVariables>({
    mutationFn: (data) => api.post('/files/presigned-upload', data),
  });
}
