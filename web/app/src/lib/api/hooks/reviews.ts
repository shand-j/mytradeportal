import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Review, ReviewStats } from '@/types';

const reviewKeys = {
  all: ['reviews'] as const,
  stats: ['reviews', 'stats'] as const,
};

export function useReviews() {
  return useQuery<Review[], ApiError>({
    queryKey: reviewKeys.all,
    queryFn: () => api.get('/reviews'),
  });
}

export type CreateReviewPayload = Omit<Review, 'id' | 'createdAt' | 'customer'> & {
  customerId: string;
};

export function useCreateReview() {
  const queryClient = useQueryClient();

  return useMutation<Review, ApiError, CreateReviewPayload>({
    mutationFn: (data) => api.post('/reviews', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.all });
      queryClient.invalidateQueries({ queryKey: reviewKeys.stats });
    },
  });
}

export function useReviewStats() {
  return useQuery<ReviewStats, ApiError>({
    queryKey: reviewKeys.stats,
    queryFn: () => api.get('/reviews/stats'),
  });
}
