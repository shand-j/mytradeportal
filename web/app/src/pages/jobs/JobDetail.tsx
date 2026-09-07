import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Calendar, MapPin, User, FileText, Edit, CheckCircle, XCircle, X } from 'lucide-react';
import { useJob, useTransitionJobStatus, useUpdateJob } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { formatGBP } from '@/lib/utils';
import { toast } from 'sonner';
import type { Job, JobStatus } from '@/types';

export function JobDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: job, isLoading, error } = useJob(id);
  const updateJob = useUpdateJob();
  const startJob = useTransitionJobStatus('start');
  const completeJob = useTransitionJobStatus('complete');
  const cancelJob = useTransitionJobStatus('cancel');
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setPageTitle('Job Detail');
  }, [setPageTitle]);

  if (isLoading) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error || !job) return <div className="text-center py-12 text-[#A8A29E]">Job not found</div>;

  const handleUpdate = (data: Partial<typeof job>) => {
    updateJob.mutate(
      { id, data },
      {
        onSuccess: () => {
          toast.success('Job updated');
          setIsEditing(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to update job'),
      }
    );
  };

  const handleTransition = (action: 'start' | 'complete' | 'cancel') => {
    const mutation = action === 'start' ? startJob : action === 'complete' ? completeJob : cancelJob;
    const label = action === 'start' ? 'started' : action === 'complete' ? 'completed' : 'cancelled';
    mutation.mutate(job.id, {
      onSuccess: () => toast.success(`Job ${label}`),
      onError: (err) => toast.error(err.message || 'Failed to update job'),
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/jobs" className="text-[#78716C] hover:text-[#D4650A]">Jobs</Link>
        <span className="text-[#A8A29E]">/</span>
        <span className="font-mono text-[#1C1917]">{job.reference}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="font-mono text-lg font-semibold text-[#1C1917]">{job.reference}</div>
                <StatusPill status={job.status} />
              </div>
              <div className="text-2xl font-bold text-[#1C1917]">{formatGBP(job.value)}</div>
            </div>
            <h3 className="text-lg font-semibold text-[#1C1917] mb-1">{job.serviceType}</h3>
            <p className="text-sm text-[#57534E] mb-4">{job.description}</p>
            <div className="grid grid-cols-2 gap-3 pt-4 border-t border-[#F0EFEA]">
              <div className="flex items-center gap-2 text-sm text-[#57534E]">
                <Calendar className="w-4 h-4 text-[#A8A29E]" />
                {job.scheduledDate} {job.scheduledTimeStart && `· ${job.scheduledTimeStart}`}
              </div>
              <div className="flex items-center gap-2 text-sm text-[#57534E]">
                <MapPin className="w-4 h-4 text-[#A8A29E]" />
                {job.propertyAddress}
              </div>
              <div className="flex items-center gap-2 text-sm text-[#57534E]">
                <User className="w-4 h-4 text-[#A8A29E]" />
                {job.technicianName || 'Unassigned'}
              </div>
              {job.quoteId && (
                <div className="flex items-center gap-2 text-sm">
                  <FileText className="w-4 h-4 text-[#A8A29E]" />
                  <Link to={`/quotes/${job.quoteId}`} className="text-[#D4650A] hover:underline">View Quote</Link>
                </div>
              )}
            </div>
          </div>

          {job.photos.length > 0 && (
            <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Job Photos</h3>
              <div className="grid grid-cols-2 gap-3">
                {job.photos.map((photo, i) => (
                  <img key={i} src={photo} alt="" className="rounded-lg object-cover h-48 w-full" />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Customer</h3>
            <div className="flex items-center gap-3 mb-3">
              {job.customer.avatarUrl ? (
                <img src={job.customer.avatarUrl} alt="" className="w-12 h-12 rounded-full object-cover" />
              ) : (
                <div className="w-12 h-12 rounded-full bg-[#F5F4F0] flex items-center justify-center text-sm font-semibold text-[#57534E]">
                  {job.customer.firstName[0]}{job.customer.lastName[0]}
                </div>
              )}
              <div>
                <div className="text-sm font-semibold text-[#1C1917]">{job.customer.firstName} {job.customer.lastName}</div>
                <div className="text-xs text-[#78716C]">{job.customer.phone}</div>
              </div>
            </div>
            <Link to={`/customers/${job.customer.id}`} className="text-xs text-[#D4650A] hover:underline">View Customer Profile</Link>
          </div>

          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Actions</h3>
            <div className="space-y-2">
              <button onClick={() => setIsEditing(true)} disabled={updateJob.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50">
                <Edit className="w-4 h-4" /> Update Status
              </button>
              {job.status === 'scheduled' && (
                <button onClick={() => handleTransition('start')} disabled={startJob.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold hover:bg-[#EFEEE9] transition-colors disabled:opacity-50">
                  <CheckCircle className="w-4 h-4" /> Start Job
                </button>
              )}
              {job.status === 'in_progress' && (
                <button onClick={() => handleTransition('complete')} disabled={completeJob.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold hover:bg-[#EFEEE9] transition-colors disabled:opacity-50">
                  <CheckCircle className="w-4 h-4" /> Mark Complete
                </button>
              )}
              {(job.status === 'scheduled' || job.status === 'in_progress') && (
                <button onClick={() => handleTransition('cancel')} disabled={cancelJob.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-[#DC2626] text-xs font-medium hover:bg-[#FEF2F2] transition-colors disabled:opacity-50">
                  <XCircle className="w-4 h-4" /> Cancel Job
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {isEditing && <JobEditDialog job={job} onClose={() => setIsEditing(false)} onSubmit={handleUpdate} isSubmitting={updateJob.isPending} />}
    </div>
  );
}

function JobEditDialog({
  job,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  job: Pick<Job, 'serviceType' | 'description' | 'scheduledDate' | 'propertyAddress' | 'value' | 'technicianName' | 'status'>;
  onClose: () => void;
  onSubmit: (data: Partial<Job>) => void;
  isSubmitting: boolean;
}) {
  const [serviceType, setServiceType] = useState(job.serviceType);
  const [description, setDescription] = useState(job.description ?? '');
  const [scheduledDate, setScheduledDate] = useState(job.scheduledDate);
  const [propertyAddress, setPropertyAddress] = useState(job.propertyAddress);
  const [value, setValue] = useState(job.value);
  const [technicianName, setTechnicianName] = useState(job.technicianName ?? '');
  const [status, setStatus] = useState<JobStatus>(job.status);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">Edit Job</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <input placeholder="Service type" value={serviceType} onChange={e => setServiceType(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <textarea placeholder="Description" value={description} onChange={e => setDescription(e.target.value)} rows={3} className="w-full px-3 py-2 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="date" value={scheduledDate} onChange={e => setScheduledDate(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Property address" value={propertyAddress} onChange={e => setPropertyAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="number" min={0} placeholder="Value (£)" value={value} onChange={e => setValue(Number(e.target.value))} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Technician name" value={technicianName} onChange={e => setTechnicianName(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <select value={status} onChange={e => setStatus(e.target.value as JobStatus)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
            <option value="scheduled">Scheduled</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !serviceType}
            onClick={() => onSubmit({ serviceType, description: description || null, scheduledDate, propertyAddress, value, technicianName: technicianName || null, status })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
