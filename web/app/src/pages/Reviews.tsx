import { useEffect, useState } from 'react';
import { Star, CheckCircle, Clock, Plus, X } from 'lucide-react';
import { useReviews, useReviewStats, useCreateReview } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { toast } from 'sonner';
import type { ReviewPlatform } from '@/types';

const platforms: ReviewPlatform[] = ['google', 'trustpilot', 'yell', 'facebook'];

export function Reviews() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: reviews, isLoading: reviewsLoading, error: reviewsError } = useReviews();
  const { data: stats, isLoading: statsLoading } = useReviewStats();
  const createReview = useCreateReview();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  useEffect(() => {
    setPageTitle('Reviews');
  }, [setPageTitle]);

  const handleCreate = (payload: {
    customerId: string;
    platform: ReviewPlatform;
    rating: number;
    reviewText: string;
    reviewerName: string;
    reviewDate: string;
  }) => {
    createReview.mutate(
      { ...payload, responded: false, responseText: null, respondedAt: null },
      {
        onSuccess: () => {
          toast.success('Review created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create review'),
      }
    );
  };

  if ((reviewsLoading || statsLoading) && !reviews) {
    return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  }

  if (reviewsError) return <div className="text-center py-12 text-[#DC2626]">Failed to load reviews</div>;

  const displayStats = stats ?? {
    averageRating: reviews && reviews.length > 0 ? reviews.reduce((s, r) => s + r.rating, 0) / reviews.length : 0,
    totalReviews: reviews?.length ?? 0,
    thisMonthCount: 0,
    thisMonthChange: 0,
    responseRate: 0,
    platformBreakdown: [],
  };

  const respondedCount = reviews?.filter(r => r.responded).length ?? 0;
  const needsResponseCount = (reviews?.length ?? 0) - respondedCount;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-[#1C1917]">Reviews</h2>
        <button
          onClick={() => setIsDialogOpen(true)}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Review
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm text-center">
          <div className="text-3xl font-bold text-[#1C1917]">{displayStats.averageRating.toFixed(1)}</div>
          <div className="flex justify-center gap-0.5 mt-1">
            {[1, 2, 3, 4, 5].map(s => (
              <Star key={s} className={`w-4 h-4 ${s <= Math.round(displayStats.averageRating) ? 'text-amber-400 fill-amber-400' : 'text-[#E7E5E4]'}`} />
            ))}
          </div>
          <div className="text-xs text-[#78716C] mt-1">{displayStats.totalReviews} reviews</div>
        </div>
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm text-center">
          <div className="text-3xl font-bold text-[#16A34A]">{respondedCount}</div>
          <div className="text-xs text-[#78716C] mt-1">Responded</div>
        </div>
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm text-center">
          <div className="text-3xl font-bold text-[#D4650A]">{needsResponseCount}</div>
          <div className="text-xs text-[#78716C] mt-1">Need Response</div>
        </div>
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm text-center">
          <div className="text-3xl font-bold text-[#2563EB]">{Math.round((respondedCount / (displayStats.totalReviews || 1)) * 100)}%</div>
          <div className="text-xs text-[#78716C] mt-1">Response Rate</div>
        </div>
      </div>

      {/* Reviews Table */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-[#F5F4F0]">
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Customer</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Rating</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Review</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Date</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Status</th>
              </tr>
            </thead>
            <tbody>
              {(reviews ?? []).map(review => (
                <tr key={review.id} className="border-t border-[#F0EFEA] hover:bg-[#F5F4F0] transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {review.customer.avatarUrl ? (
                        <img src={review.customer.avatarUrl} alt="" className="w-7 h-7 rounded-full object-cover" />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-[#F5F4F0] flex items-center justify-center text-[11px] font-semibold text-[#57534E]">
                          {review.customer.firstName[0]}{review.customer.lastName[0]}
                        </div>
                      )}
                      <div className="text-sm font-medium text-[#1C1917]">{review.customer.firstName} {review.customer.lastName}</div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => (
                        <Star key={s} className={`w-3.5 h-3.5 ${s <= review.rating ? 'text-amber-400 fill-amber-400' : 'text-[#E7E5E4]'}`} />
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <div className="text-sm text-[#57534E] truncate">{review.reviewText}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-[#78716C]">{new Date(review.reviewDate).toLocaleDateString('en-GB')}</td>
                  <td className="px-4 py-3">
                    {review.responded ? (
                      <span className="inline-flex items-center gap-1 text-xs text-[#16A34A] font-medium">
                        <CheckCircle className="w-3.5 h-3.5" /> Responded
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-[#D4650A] font-medium">
                        <Clock className="w-3.5 h-3.5" /> Needs Reply
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(!reviews || reviews.length === 0) && (
          <div className="py-12 text-center text-sm text-[#A8A29E]">No reviews found</div>
        )}
      </div>

      {isDialogOpen && <ReviewDialog onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createReview.isPending} />}
    </div>
  );
}

function ReviewDialog({
  onClose,
  onSubmit,
  isSubmitting,
}: {
  onClose: () => void;
  onSubmit: (payload: {
    customerId: string;
    platform: ReviewPlatform;
    rating: number;
    reviewText: string;
    reviewerName: string;
    reviewDate: string;
  }) => void;
  isSubmitting: boolean;
}) {
  const [customerId, setCustomerId] = useState('');
  const [platform, setPlatform] = useState<ReviewPlatform>('google');
  const [rating, setRating] = useState(5);
  const [reviewText, setReviewText] = useState('');
  const [reviewerName, setReviewerName] = useState('');
  const [reviewDate, setReviewDate] = useState(new Date().toISOString().split('T')[0]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">Add Review</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Customer ID</label>
            <input value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Reviewer Name</label>
            <input value={reviewerName} onChange={e => setReviewerName(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Platform</label>
              <select value={platform} onChange={e => setPlatform(e.target.value as ReviewPlatform)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
                {platforms.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Rating</label>
              <select value={rating} onChange={e => setRating(Number(e.target.value))} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
                {[1, 2, 3, 4, 5].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Review Date</label>
            <input type="date" value={reviewDate} onChange={e => setReviewDate(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Review Text</label>
            <textarea value={reviewText} onChange={e => setReviewText(e.target.value)} rows={3} className="w-full px-3 py-2 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !customerId || !reviewerName}
            onClick={() => onSubmit({ customerId, platform, rating, reviewText, reviewerName, reviewDate })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Save Review'}
          </button>
        </div>
      </div>
    </div>
  );
}
