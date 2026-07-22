import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, CalendarPlus, X, Trash2 } from 'lucide-react';
import {
  useAppointments,
  useCreateAppointment,
  useUpdateAppointment,
  useDeleteAppointment,
  useAvailability,
  useContacts,
} from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isToday, startOfWeek, endOfWeek, addMonths, subMonths, addDays } from 'date-fns';
import { toast } from 'sonner';
import type { Appointment, AppointmentStatus } from '@/types';

type CalendarView = 'month' | 'week' | 'day';

const appointmentStatuses: AppointmentStatus[] = ['scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show'];

export function Calendar() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: appointments, isLoading, error } = useAppointments();
  const createAppointment = useCreateAppointment();
  const updateAppointment = useUpdateAppointment();
  const deleteAppointment = useDeleteAppointment();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState<CalendarView>('month');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedAppt, setSelectedAppt] = useState<Appointment | null>(null);

  useEffect(() => {
    setPageTitle('Calendar');
  }, [setPageTitle]);

  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 });
  const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

  const getApptsForDay = (day: Date) => (appointments ?? []).filter(a => {
    const d = new Date(a.startTime);
    return d.getDate() === day.getDate() && d.getMonth() === day.getMonth() && d.getFullYear() === day.getFullYear();
  });

  const statusColors: Record<string, string> = {
    scheduled: 'bg-[#FFF7ED] text-[#C2410C]',
    confirmed: 'bg-[#F0FDF4] text-[#15803D]',
    in_progress: 'bg-[#EFF6FF] text-[#1D4ED8]',
    completed: 'bg-[#F0FDF4] text-[#15803D]',
    cancelled: 'bg-[#FEF2F2] text-[#B91C1C]',
  };

  const setViewFromLabel = (label: string) => {
    const lower = label.toLowerCase();
    if (lower === 'month' || lower === 'week' || lower === 'day') {
      setView(lower);
    }
  };

  const handleCreate = (payload: {
    customerId: string;
    title: string;
    startTime: string;
    endTime: string;
    serviceType: string;
    propertyAddress: string;
    status: AppointmentStatus;
    technicianName: string;
  }) => {
    createAppointment.mutate(
      { ...payload, jobId: null },
      {
        onSuccess: () => {
          toast.success('Appointment created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create appointment'),
      }
    );
  };

  const handleUpdate = (id: string, data: Partial<Appointment>) => {
    updateAppointment.mutate(
      { id, data },
      {
        onSuccess: () => {
          toast.success('Appointment updated');
          setSelectedAppt(null);
        },
        onError: (err) => toast.error(err.message || 'Failed to update appointment'),
      }
    );
  };

  const handleDelete = (id: string) => {
    if (!confirm('Delete this appointment?')) return;
    deleteAppointment.mutate(id, {
      onSuccess: () => {
        toast.success('Appointment deleted');
        setSelectedAppt(null);
      },
      onError: (err) => toast.error(err.message || 'Failed to delete appointment'),
    });
  };

  if (isLoading && !appointments) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load appointments</div>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-[#1C1917]">{format(currentDate, 'MMMM yyyy')}</h2>
          <div className="flex items-center gap-1">
            <button onClick={() => setCurrentDate(subMonths(currentDate, 1))} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[#F5F4F0] transition-colors">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button onClick={() => setCurrentDate(new Date())} className="px-3 h-8 text-xs font-medium rounded-lg hover:bg-[#F5F4F0] transition-colors text-[#57534E]">
              Today
            </button>
            <button onClick={() => setCurrentDate(addMonths(currentDate, 1))} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[#F5F4F0] transition-colors">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(['Month', 'Week', 'Day'] as const).map(v => (
            <button key={v} onClick={() => setViewFromLabel(v)} className={`px-3 h-8 text-xs font-medium rounded-lg transition-colors ${
              view === v.toLowerCase() ? 'bg-[#1C1917] text-white' : 'text-[#57534E] hover:bg-[#F5F4F0]'
            }`}>
              {v}
            </button>
          ))}
          <button
            onClick={() => setIsDialogOpen(true)}
            className="h-8 px-3 flex items-center gap-1.5 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors"
          >
            <CalendarPlus className="w-3.5 h-3.5" />
            New Appointment
          </button>
        </div>
      </div>

      {/* Month View */}
      {view === 'month' && (
        <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm overflow-hidden">
          {/* Weekday headers */}
          <div className="grid grid-cols-7 border-b border-[#F0EFEA]">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => (
              <div key={d} className="py-2.5 text-center text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">{d}</div>
            ))}
          </div>
          {/* Days grid */}
          <div className="grid grid-cols-7" style={{ gap: '1px', background: '#F0EFEA' }}>
            {days.map(day => {
              const appts = getApptsForDay(day);
              const isCurrentMonth = isSameMonth(day, currentDate);
              return (
                <div key={day.toISOString()} className={`bg-white min-h-[120px] p-1.5 ${!isCurrentMonth ? 'opacity-40' : ''}`}>
                  <div className={`w-7 h-7 flex items-center justify-center rounded-full text-xs font-medium mb-1 ${
                    isToday(day) ? 'bg-[#D4650A] text-white' : 'text-[#57534E]'
                  }`}>
                    {format(day, 'd')}
                  </div>
                  <div className="space-y-1">
                    {appts.slice(0, 3).map(appt => (
                      <button
                        key={appt.id}
                        onClick={() => setSelectedAppt(appt)}
                        className={`block w-full text-left px-1.5 py-0.5 rounded text-[10px] font-medium truncate ${statusColors[appt.status] || ''}`}
                      >
                        {appt.title}
                      </button>
                    ))}
                    {appts.length > 3 && <div className="text-[10px] text-[#A8A29E] px-1.5">+{appts.length - 3} more</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {view === 'week' && <WeekView currentDate={currentDate} appointments={appointments ?? []} onSelect={setSelectedAppt} />}
      {view === 'day' && <DayView currentDate={currentDate} appointments={appointments ?? []} onSelect={setSelectedAppt} />}

      {isDialogOpen && <AppointmentDialog onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createAppointment.isPending} initialDate={currentDate} />}
      {selectedAppt && <AppointmentEditDialog appointment={selectedAppt} onClose={() => setSelectedAppt(null)} onSubmit={handleUpdate} onDelete={handleDelete} isSubmitting={updateAppointment.isPending} />}
    </div>
  );
}

interface ViewProps {
  currentDate: Date;
  appointments: Appointment[];
  onSelect: (appt: Appointment) => void;
}

function WeekView({ currentDate, appointments, onSelect }: ViewProps) {
  const statusColors: Record<string, string> = {
    scheduled: 'bg-[#FFF7ED] text-[#C2410C]',
    confirmed: 'bg-[#F0FDF4] text-[#15803D]',
    in_progress: 'bg-[#EFF6FF] text-[#1D4ED8]',
    completed: 'bg-[#F0FDF4] text-[#15803D]',
    cancelled: 'bg-[#FEF2F2] text-[#B91C1C]',
  };
  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const hours = Array.from({ length: 13 }, (_, i) => i + 7);

  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm overflow-hidden">
      <div className="grid grid-cols-8 border-b border-[#F0EFEA]">
        <div className="py-2.5 px-2 text-[11px] font-semibold text-[#A8A29E] uppercase">Time</div>
        {days.map(d => (
          <div key={d.toISOString()} className={`py-2.5 text-center text-xs font-medium ${isToday(d) ? 'text-[#D4650A]' : 'text-[#57534E]'}`}>
            {format(d, 'EEE d')}
          </div>
        ))}
      </div>
      <div className="max-h-[600px] overflow-y-auto">
        {hours.map(hour => (
          <div key={hour} className="grid grid-cols-8 border-b border-[#F0EFEA]" style={{ minHeight: '60px' }}>
            <div className="px-2 py-2 text-[11px] text-[#A8A29E] font-medium">{hour}:00</div>
            {days.map(day => {
              const appts = appointments.filter(a => {
                const d = new Date(a.startTime);
                return d.getDate() === day.getDate() && d.getMonth() === day.getMonth() && d.getHours() === hour;
              });
              return (
                <div key={day.toISOString()} className="border-l border-[#F0EFEA] p-1 relative">
                  {appts.map(appt => (
                    <button
                      key={appt.id}
                      onClick={() => onSelect(appt)}
                      className={`block w-full text-left px-1.5 py-1 rounded text-[10px] font-medium truncate ${statusColors[appt.status] || ''}`}
                    >
                      {appt.title}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function DayView({ currentDate, appointments, onSelect }: ViewProps) {
  const dayAppts = appointments.filter(a => {
    const d = new Date(a.startTime);
    return d.getDate() === currentDate.getDate() && d.getMonth() === currentDate.getMonth();
  }).sort((a, b) => new Date(a.startTime).getTime() - new Date(b.startTime).getTime());

  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm p-5 space-y-3">
      <div className="text-sm font-medium text-[#78716C] mb-4">{format(currentDate, 'EEEE, MMMM do')}</div>
      {dayAppts.length === 0 && <div className="text-sm text-[#A8A29E] py-8 text-center">No appointments scheduled</div>}
      {dayAppts.map(appt => (
        <button
          key={appt.id}
          onClick={() => onSelect(appt)}
          className="w-full flex items-center gap-4 p-4 rounded-lg border border-[#E7E5E4] hover:bg-[#F5F4F0] transition-colors text-left"
        >
          <div className={`w-1 h-12 rounded-full ${appt.status === 'in_progress' ? 'bg-[#2563EB]' : appt.status === 'completed' ? 'bg-[#16A34A]' : 'bg-[#D4650A]'}`} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-[#1C1917]">{appt.title}</div>
            <div className="text-xs text-[#78716C]">{appt.customer.firstName} {appt.customer.lastName} · {appt.propertyAddress}</div>
          </div>
          <div className="text-xs text-[#57534E] font-medium">
            {format(new Date(appt.startTime), 'HH:mm')} - {format(new Date(appt.endTime), 'HH:mm')}
          </div>
        </button>
      ))}
    </div>
  );
}

function AppointmentDialog({
  onClose,
  onSubmit,
  isSubmitting,
  initialDate,
}: {
  onClose: () => void;
  onSubmit: (payload: {
    customerId: string;
    title: string;
    startTime: string;
    endTime: string;
    serviceType: string;
    propertyAddress: string;
    status: AppointmentStatus;
    technicianName: string;
  }) => void;
  isSubmitting: boolean;
  initialDate: Date;
}) {
  const { data: contacts } = useContacts();
  const { data: availability } = useAvailability(initialDate.toISOString().split('T')[0]);
  const [customerId, setCustomerId] = useState('');
  const [title, setTitle] = useState('');
  const [date, setDate] = useState(initialDate.toISOString().split('T')[0]);
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('10:00');
  const [serviceType, setServiceType] = useState('');
  const [propertyAddress, setPropertyAddress] = useState('');
  const [status, setStatus] = useState<AppointmentStatus>('scheduled');
  const [technicianName, setTechnicianName] = useState('');

  const buildDateTime = (d: string, t: string) => `${d}T${t}:00`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">New Appointment</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Customer</label>
            <select value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              <option value="">Select customer</option>
              {(contacts ?? []).map(c => <option key={c.id} value={c.id}>{c.firstName} {c.lastName}</option>)}
            </select>
          </div>
          <input placeholder="Title" value={title} onChange={e => setTitle(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Start</label>
              <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">End</label>
              <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            </div>
          </div>
          {availability && availability.length > 0 && (
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Available Slots</label>
              <div className="flex flex-wrap gap-1">
                {availability.slice(0, 8).map((slot, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setStartTime(slot.startTime.slice(0, 5));
                      setEndTime(slot.endTime.slice(0, 5));
                    }}
                    className="text-[10px] px-2 py-1 rounded bg-[#F5F4F0] hover:bg-[#FFF7ED] text-[#57534E]"
                  >
                    {slot.startTime.slice(0, 5)} - {slot.endTime.slice(0, 5)}
                  </button>
                ))}
              </div>
            </div>
          )}
          <input placeholder="Service type" value={serviceType} onChange={e => setServiceType(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Property address" value={propertyAddress} onChange={e => setPropertyAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Technician name" value={technicianName} onChange={e => setTechnicianName(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <select value={status} onChange={e => setStatus(e.target.value as AppointmentStatus)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
            {appointmentStatuses.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !customerId || !title}
            onClick={() => onSubmit({ customerId, title, startTime: buildDateTime(date, startTime), endTime: buildDateTime(date, endTime), serviceType, propertyAddress, status, technicianName })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Create Appointment'}
          </button>
        </div>
      </div>
    </div>
  );
}

function AppointmentEditDialog({
  appointment,
  onClose,
  onSubmit,
  onDelete,
  isSubmitting,
}: {
  appointment: Appointment;
  onClose: () => void;
  onSubmit: (id: string, data: Partial<Appointment>) => void;
  onDelete: (id: string) => void;
  isSubmitting: boolean;
}) {
  const { data: contacts } = useContacts();
  const [customerId, setCustomerId] = useState(appointment.customerId);
  const [title, setTitle] = useState(appointment.title);
  const [date, setDate] = useState(appointment.startTime.slice(0, 10));
  const [startTime, setStartTime] = useState(appointment.startTime.slice(11, 16));
  const [endTime, setEndTime] = useState(appointment.endTime.slice(11, 16));
  const [serviceType, setServiceType] = useState(appointment.serviceType);
  const [propertyAddress, setPropertyAddress] = useState(appointment.propertyAddress);
  const [status, setStatus] = useState<AppointmentStatus>(appointment.status);
  const [technicianName, setTechnicianName] = useState(appointment.technicianName ?? '');

  const buildDateTime = (d: string, t: string) => `${d}T${t}:00`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">Edit Appointment</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Customer</label>
            <select value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              <option value="">Select customer</option>
              {(contacts ?? []).map(c => <option key={c.id} value={c.id}>{c.firstName} {c.lastName}</option>)}
            </select>
          </div>
          <input placeholder="Title" value={title} onChange={e => setTitle(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Start</label>
              <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">End</label>
              <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            </div>
          </div>
          <input placeholder="Service type" value={serviceType} onChange={e => setServiceType(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Property address" value={propertyAddress} onChange={e => setPropertyAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Technician name" value={technicianName} onChange={e => setTechnicianName(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <select value={status} onChange={e => setStatus(e.target.value as AppointmentStatus)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
            {appointmentStatuses.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div className="flex justify-between items-center pt-2">
          <button onClick={() => onDelete(appointment.id)} className="h-9 px-4 text-sm font-medium text-[#DC2626] hover:bg-[#FEF2F2] rounded-lg flex items-center gap-1"><Trash2 className="w-4 h-4" /> Delete</button>
          <div className="flex gap-2">
            <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
            <button
              disabled={isSubmitting || !customerId || !title}
              onClick={() => onSubmit(appointment.id, { customerId, title, startTime: buildDateTime(date, startTime), endTime: buildDateTime(date, endTime), serviceType, propertyAddress, status, technicianName: technicianName || null })}
              className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
            >
              {isSubmitting ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
