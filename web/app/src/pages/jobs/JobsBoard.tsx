import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, X } from 'lucide-react';
import { useJobs, useCreateJob, useTransitionJobStatus } from '@/lib/api/hooks';
import { useContacts } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { formatGBP } from '@/lib/utils';
import type { JobStatus } from '@/types';
import { toast } from 'sonner';

const columns: { status: JobStatus; label: string; color: string }[] = [
  { status: 'scheduled', label: 'Scheduled', color: '#D4650A' },
  { status: 'in_progress', label: 'In Progress', color: '#2563EB' },
  { status: 'completed', label: 'Completed', color: '#16A34A' },
  { status: 'cancelled', label: 'Cancelled', color: '#DC2626' },
];

export function JobsBoard() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: jobs, isLoading, error } = useJobs();
  const { data: contacts } = useContacts();
  const createJob = useCreateJob();
  const startJob = useTransitionJobStatus('start');
  const completeJob = useTransitionJobStatus('complete');
  const cancelJob = useTransitionJobStatus('cancel');
  const [search, setSearch] = useState('');
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  useEffect(() => {
    setPageTitle('Jobs');
  }, [setPageTitle]);

  const filtered = (jobs ?? []).filter(j => !search || j.customer.firstName.toLowerCase().includes(search.toLowerCase()) || j.serviceType.toLowerCase().includes(search.toLowerCase()));

  const handleCreate = (payload: {
    customerId: string;
    reference: string;
    serviceType: string;
    scheduledDate: string;
    propertyAddress: string;
    value: number;
    description: string;
  }) => {
    createJob.mutate(
      {
        ...payload,
        status: 'scheduled',
        quoteId: null,
        scheduledTimeStart: null,
        scheduledTimeEnd: null,
        technicianId: null,
        technicianName: null,
        completionNotes: null,
        photos: [],
      },
      {
        onSuccess: () => {
          toast.success('Job created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create job'),
      }
    );
  };

  const handleTransition = (id: string, action: JobStatus) => {
    const mutation = action === 'in_progress' ? startJob : action === 'completed' ? completeJob : cancelJob;
    const label = action === 'in_progress' ? 'started' : action === 'completed' ? 'completed' : 'cancelled';
    mutation.mutate(id, {
      onSuccess: () => toast.success(`Job ${label}`),
      onError: (err) => toast.error(err.message || `Failed to update job`),
    });
  };

  if (isLoading && !jobs) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load jobs</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold text-[#1C1917]">Jobs</h2>
          <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-xs font-medium text-[#57534E]">{filtered.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#A8A29E]" />
            <input type="text" placeholder="Search jobs..." value={search} onChange={e => setSearch(e.target.value)}
              className="h-9 w-56 pl-9 pr-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] focus:ring-2 focus:ring-[#FFF7ED]" />
          </div>
          <button
            onClick={() => setIsDialogOpen(true)}
            className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors"
          >
            <Plus className="w-4 h-4" /> New Job
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {columns.map(col => {
          const colJobs = filtered.filter(j => j.status === col.status);
          return (
            <div key={col.status} className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm min-h-[400px]">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#F0EFEA]">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: col.color }} />
                  <span className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em]">{col.label}</span>
                </div>
                <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-[11px] font-medium text-[#57534E]">{colJobs.length}</span>
              </div>
              <div className="p-2 space-y-2">
                {colJobs.map(job => (
                  <div key={job.id} className="block bg-white border border-[#E7E5E4] rounded-lg p-3 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200" style={{ borderLeft: `3px solid ${col.color}` }}>
                    <Link to={`/jobs/${job.id}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-[11px] text-[#A8A29E]">{job.reference}</span>
                        <span className="text-sm font-semibold text-[#1C1917]">{formatGBP(job.value)}</span>
                      </div>
                      <div className="text-sm font-medium text-[#1C1917]">{job.customer.firstName} {job.customer.lastName}</div>
                      <div className="text-xs text-[#78716C] mt-0.5">{job.serviceType}</div>
                      <div className="flex items-center gap-2 mt-2">
                        <div className="w-5 h-5 rounded-full bg-[#D4650A] flex items-center justify-center">
                          <span className="text-[9px] font-bold text-white">{job.technicianName?.[0]}</span>
                        </div>
                        <span className="text-[11px] text-[#78716C]">{job.scheduledDate}</span>
                      </div>
                    </Link>
                    <div className="flex items-center gap-1 mt-2 pt-2 border-t border-[#F0EFEA]">
                      {job.status === 'scheduled' && (
                        <button onClick={() => handleTransition(job.id, 'in_progress')} className="text-[10px] px-2 py-1 rounded bg-[#EFF6FF] text-[#1D4ED8] hover:bg-[#DBEAFE]">Start</button>
                      )}
                      {job.status === 'in_progress' && (
                        <button onClick={() => handleTransition(job.id, 'completed')} className="text-[10px] px-2 py-1 rounded bg-[#F0FDF4] text-[#15803D] hover:bg-[#DCFCE7]">Complete</button>
                      )}
                      {(job.status === 'scheduled' || job.status === 'in_progress') && (
                        <button onClick={() => handleTransition(job.id, 'cancelled')} className="text-[10px] px-2 py-1 rounded bg-[#FEF2F2] text-[#B91C1C] hover:bg-[#FECACA]">Cancel</button>
                      )}
                    </div>
                  </div>
                ))}
                {colJobs.length === 0 && <div className="text-center py-8 text-xs text-[#A8A29E]">No jobs</div>}
              </div>
            </div>
          );
        })}
      </div>

      {isDialogOpen && <JobDialog contacts={contacts ?? []} onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createJob.isPending} />}
    </div>
  );
}

function JobDialog({
  contacts,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  contacts: { id: string; firstName: string; lastName: string }[];
  onClose: () => void;
  onSubmit: (payload: {
    customerId: string;
    reference: string;
    serviceType: string;
    scheduledDate: string;
    propertyAddress: string;
    value: number;
    description: string;
  }) => void;
  isSubmitting: boolean;
}) {
  const [customerId, setCustomerId] = useState('');
  const [reference, setReference] = useState('');
  const [serviceType, setServiceType] = useState('');
  const [scheduledDate, setScheduledDate] = useState(new Date().toISOString().split('T')[0]);
  const [propertyAddress, setPropertyAddress] = useState('');
  const [value, setValue] = useState(0);
  const [description, setDescription] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">New Job</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Customer</label>
            <select value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              <option value="">Select customer</option>
              {contacts.map(c => <option key={c.id} value={c.id}>{c.firstName} {c.lastName}</option>)}
            </select>
          </div>
          <input placeholder="Reference" value={reference} onChange={e => setReference(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Service type" value={serviceType} onChange={e => setServiceType(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="date" value={scheduledDate} onChange={e => setScheduledDate(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Property address" value={propertyAddress} onChange={e => setPropertyAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="number" min={0} placeholder="Value (£)" value={value} onChange={e => setValue(Number(e.target.value))} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <textarea placeholder="Description" value={description} onChange={e => setDescription(e.target.value)} rows={3} className="w-full px-3 py-2 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !customerId || !reference || !serviceType}
            onClick={() => onSubmit({ customerId, reference, serviceType, scheduledDate, propertyAddress, value, description })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Create Job'}
          </button>
        </div>
      </div>
    </div>
  );
}
