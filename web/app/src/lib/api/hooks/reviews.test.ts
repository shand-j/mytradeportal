import { describe, it, expect } from 'vitest';

import { toReview, toReviewStats } from './reviews';

describe('toReview', () => {
  it('maps the API shape without an embedded customer', () => {
    // GET /reviews returns contact_id/comment/source/response, no customer.
    const review = toReview({
      id: 'r1',
      tenantId: 't1',
      contactId: 'c1',
      rating: 5,
      comment: 'Quoted quickly and explained everything clearly.',
      source: 'in_app',
      status: 'pending',
      response: null,
      respondedAt: null,
      createdAt: '2026-09-01T07:56:47',
      updatedAt: '2026-09-01T07:56:47',
    });

    expect(review.customerId).toBe('c1');
    expect(review.customer).toBeUndefined();
    expect(review.reviewText).toBe('Quoted quickly and explained everything clearly.');
    expect(review.rating).toBe(5);
    expect(review.responded).toBe(false);
    expect(review.reviewDate).toBe('2026-09-01T07:56:47');
  });

  it('marks reviews with a response as responded', () => {
    const review = toReview({
      id: 'r2',
      contactId: 'c1',
      rating: 5,
      comment: 'Great job.',
      source: 'google',
      response: 'Thanks for the kind words!',
      respondedAt: '2026-08-26T07:56:46',
      createdAt: '2026-09-01T07:56:47',
    });

    expect(review.responded).toBe(true);
    expect(review.responseText).toBe('Thanks for the kind words!');
  });

  it('prefers an embedded customer when present', () => {
    const review = toReview({
      id: 'r3',
      contactId: 'c1',
      rating: 4,
      comment: 'Good work.',
      customer: { id: 'c1', name: 'Emma Whitfield', phone: '07911 567890', createdAt: '2026-09-01T00:00:00' },
    });

    expect(review.customer?.firstName).toBe('Emma');
    expect(review.reviewerName).toBe('Emma Whitfield');
  });
});

describe('toReviewStats', () => {
  it('maps the API stats shape', () => {
    // GET /reviews/stats returns average_rating/total_count (camelized by the client).
    const stats = toReviewStats({
      averageRating: 4.67,
      totalCount: 3,
      pendingCount: 1,
      approvedCount: 2,
      rejectedCount: 0,
    });

    expect(stats.averageRating).toBe(4.67);
    expect(stats.totalReviews).toBe(3);
    expect(stats.platformBreakdown).toEqual([]);
  });
});
