import { useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import type { Toast } from '@/types';

const icons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const borderColors = {
  success: 'border-l-[#16A34A]',
  error: 'border-l-[#DC2626]',
  warning: 'border-l-[#EAB308]',
  info: 'border-l-[#2563EB]',
};

export function ToastContainer() {
  const toasts = useUiStore(s => s.toasts);
  const removeToast = useUiStore(s => s.removeToast);

  return (
    <div className="fixed bottom-6 right-6 z-[300] flex flex-col gap-2">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onRemove, 4000);
    return () => clearTimeout(timer);
  }, [onRemove]);

  const Icon = icons[toast.type as keyof typeof icons];

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-[#E7E5E4] border-l-[3px] ${borderColors[toast.type as keyof typeof borderColors]} shadow-lg min-w-[320px] max-w-[420px] animate-slideUp`}
    >
      <Icon className={`w-5 h-5 flex-shrink-0 ${
        toast.type === 'success' ? 'text-[#16A34A]' :
        toast.type === 'error' ? 'text-[#DC2626]' :
        toast.type === 'warning' ? 'text-[#EAB308]' :
        'text-[#2563EB]'
      }`} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-[#1C1917]">{toast.title}</div>
        {toast.message && <div className="text-xs text-[#57534E] mt-0.5">{toast.message}</div>}
      </div>
      <button onClick={onRemove} className="text-[#A8A29E] hover:text-[#1C1917] transition-colors">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
