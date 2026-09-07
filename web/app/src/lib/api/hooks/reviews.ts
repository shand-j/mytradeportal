import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Review, ReviewStats } from '@/types';

import { toCustomer } from './contacts';

const reviewKeys = {
  all: ['reviews'] as const,
  stats: ['reviews', 'stats'] as const,
};

export function toReview(raw: Record<string, unknown>): Review {
  // The API does not embed a customer object on reviews; fall back to the
  // reviewer name (or leave undefined and let the UI render a placeholder).
  const reviewerName = String(raw.reviewerName ?? raw.reviewer_name ?? '');
  const customer = raw.customer
    ? toCustomer(raw.customer as Record<string, unknown>)
    : undefined;
  const responseText = (raw.responseText ?? raw.response ?? null) as string | null;
  const respondedAt = (raw.respondedAt ?? raw.responded_at ?? null) as string | null;

  return {
    id: String(raw.id),
    customerId: String(raw.customerId ?? raw.contactId ?? raw.contact_id ?? ''),
    customer,
    platform: (raw.platform ?? raw.source ?? 'google') as Review['platform'],
    rating: Number(raw.rating ?? 0),
    reviewText: String(raw.reviewText ?? raw.review_text ?? raw.comment ?? ''),
    reviewerName: reviewerName || (customer ? `${customer.firstName} ${customer.lastName}`.trim() : ''),
    responded: Boolean(raw.responded ?? responseText ?? respondedAt),
    responseText,
    respondedAt,
    reviewDate: String(raw.reviewDate ?? raw.review_date ?? raw.createdAt ?? raw.created_at ?? ''),
  };
}

export function toReviewStats(raw: Record<string, unknown>): ReviewStats {
  return {
    averageRating: Number(raw.averageRating ?? raw.average_rating ?? 0),
    totalReviews: Number(raw.totalReviews ?? raw.totalCount ?? raw.total_count ?? 0),
    thisMonthCount: Number(raw.thisMonthCount ?? raw.this_month_count ?? 0),
    thisMonthChange: Number(raw.thisMonthChange ?? raw.this_month_change ?? 0),
    responseRate: Number(raw.responseRate ?? raw.response_rate ?? 0),
    platformBreakdown: Array.isArray(raw.platformBreakdown)
      ? (raw.platformBreakdown as ReviewStats['platformBreakdown'])
      : [],
  };
}

export function useReviews() {
  return useQuery<Review[], ApiError>({
    queryKey: reviewKeys.all,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>[]>('/reviews');
      return data.map(toReview);
    },
  });
}

export type CreateReviewPayload = Omit<Review, 'id' | 'createdAt' | 'customer'> & {
  customerId: string;
};

export function useCreateReview() {
  const queryClient = useQueryClient();

  return useMutation<Review, ApiError, CreateReviewPayload>({
    mutationFn: async (data) => {
      const raw = await api.post<Record<string, unknown>>('/reviews', {
        contact_id: data.customerId,
        rating: data.rating,
        comment: data.reviewText,
        source: data.platform,
      });
      return toReview(raw);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.all });
      queryClient.invalidateQueries({ queryKey: reviewKeys.stats });
    },
  });
}

export function useReviewStats() {
  return useQuery<ReviewStats, ApiError>({
    queryKey: reviewKeys.stats,
    queryFn: async () => {
      const data = await api.get<Record<string, unknown>>('/reviews/stats');
      return toReviewStats(data);
    },
  });
}
