import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Reviews } from './Reviews';
import { useReviews, useCreateReview } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockReviews } from '@/lib/mock/data/reviews';
import { mockReviewStats } from '@/test/fixtures';

const defaultMutations = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  error: null,
  data: undefined,
  status: 'idle',
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useReviews: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useReviewStats: vi.fn(() => ({ data: mockReviewStats, isLoading: false, error: null })),
    useCreateReview: vi.fn(() => defaultMutations),
  };
});

describe('Reviews', () => {
  beforeEach(() => {
    resetStores();
    vi.mocked(useReviews).mockReturnValue({ data: mockReviews, isLoading: false, error: null });
    vi.mocked(useCreateReview).mockReturnValue(defaultMutations);
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useReviews).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<Reviews />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useReviews).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<Reviews />);
    expect(screen.getByText('Failed to load reviews')).toBeInTheDocument();
  });

  it('renders reviews from mock data', () => {
    renderPage(<Reviews />);
    expect(screen.getByText('Reviews')).toBeInTheDocument();
    expect(screen.getAllByText('Sarah Johnson').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('David Smith')).toBeInTheDocument();
  });

  it('renders a review without an embedded customer (API shape)', () => {
    // GET /reviews returns no customer object; only reviewer/contact fields.
    const apiReview = {
      ...mockReviews[0],
      customer: undefined,
      reviewerName: 'Peter Okafor',
    };
    vi.mocked(useReviews).mockReturnValue({ data: [apiReview], isLoading: false, error: null });
    renderPage(<Reviews />);
    expect(screen.getByText('Peter Okafor')).toBeInTheDocument();
    expect(screen.getByText('PO')).toBeInTheDocument();
  });

  it('falls back to a placeholder when neither customer nor reviewer name exists', () => {
    const apiReview = {
      ...mockReviews[0],
      customer: undefined,
      reviewerName: '',
    };
    vi.mocked(useReviews).mockReturnValue({ data: [apiReview], isLoading: false, error: null });
    renderPage(<Reviews />);
    // Table header is also "Customer"; the row must add a second occurrence.
    expect(screen.getAllByText('Customer').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('C')).toBeInTheDocument();
  });

  it('opens and closes the add review dialog', async () => {
    const user = userEvent.setup();
    renderPage(<Reviews />);

    await user.click(screen.getByRole('button', { name: /add review/i }));
    expect(screen.getByRole('heading', { name: 'Add Review' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('heading', { name: 'Add Review' })).not.toBeInTheDocument();
  });
});
