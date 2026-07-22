import type { QuoteStatus, JobStatus, InvoiceStatus, AppointmentStatus } from '@/types';

type AnyStatus = QuoteStatus | JobStatus | InvoiceStatus | AppointmentStatus;

const config: Record<string, { bg: string; text: string }> = {
  draft: { bg: 'bg-[#FEFCE8]', text: 'text-[#A16207]' },
  sent: { bg: 'bg-[#EFF6FF]', text: 'text-[#1D4ED8]' },
  accepted: { bg: 'bg-[#F0FDF4]', text: 'text-[#15803D]' },
  rejected: { bg: 'bg-[#FEF2F2]', text: 'text-[#B91C1C]' },
  expired: { bg: 'bg-[#F5F5F4]', text: 'text-[#78716C]' },
  scheduled: { bg: 'bg-[#FFF7ED]', text: 'text-[#C2410C]' },
  in_progress: { bg: 'bg-[#EFF6FF]', text: 'text-[#1D4ED8]' },
  completed: { bg: 'bg-[#F0FDF4]', text: 'text-[#15803D]' },
  cancelled: { bg: 'bg-[#FEF2F2]', text: 'text-[#B91C1C]' },
  viewed: { bg: 'bg-[#F5F3FF]', text: 'text-[#7C3AED]' },
  paid: { bg: 'bg-[#F0FDF4]', text: 'text-[#15803D]' },
  overdue: { bg: 'bg-[#FEF2F2]', text: 'text-[#B91C1C]' },
  confirmed: { bg: 'bg-[#F0FDF4]', text: 'text-[#15803D]' },
  no_show: { bg: 'bg-[#FEF2F2]', text: 'text-[#B91C1C]' },
};

export function StatusPill({ status }: { status: AnyStatus }) {
  const c = config[status] || { bg: 'bg-[#F5F5F4]', text: 'text-[#78716C]' };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-[0.05em] ${c.bg} ${c.text}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}
