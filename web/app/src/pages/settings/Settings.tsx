import { useEffect, useState } from 'react';
import { Building2, Paintbrush, Wrench, Link2, CheckCircle, XCircle, RefreshCw, Save, Plus } from 'lucide-react';
import { useSettings, useUpdateSettings, useFeatureFlags } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { toast } from 'sonner';
import type { IntegrationStatus, ServiceOffering, Tenant } from '@/types';

const tabs = [
  { id: 'business', label: 'Business', icon: Building2 },
  { id: 'branding', label: 'Branding', icon: Paintbrush },
  { id: 'services', label: 'Services', icon: Wrench },
  { id: 'integrations', label: 'Integrations', icon: Link2 },
];

const initialServices: ServiceOffering[] = [
  { id: 'svc-1', name: 'Boiler Installation', description: 'Full boiler installation', basePrice: 1200, estimatedDuration: 240, category: 'Heating', isActive: true },
  { id: 'svc-2', name: 'Annual Service', description: 'Annual boiler service', basePrice: 120, estimatedDuration: 60, category: 'Maintenance', isActive: true },
  { id: 'svc-3', name: 'Emergency Repair', description: 'Out of hours emergency repair', basePrice: 200, estimatedDuration: 90, category: 'Repairs', isActive: true },
];

const initialIntegrations: IntegrationStatus[] = [
  { provider: 'quickbooks', connected: true, accountName: 'QuickBooks Online', accountIdentifier: 'Mikes Plumbing Ltd', lastSyncAt: '2025-06-20T10:00:00Z' },
  { provider: 'xero', connected: false, accountName: null, accountIdentifier: null, lastSyncAt: null },
  { provider: 'stripe', connected: true, accountName: 'Stripe', accountIdentifier: '...4242', lastSyncAt: '2025-06-20T15:00:00Z' },
  { provider: 'twilio', connected: true, accountName: 'Twilio', accountIdentifier: '+44 20 7946 0123', lastSyncAt: '2025-06-19T08:00:00Z' },
  { provider: 'whatsapp', connected: true, accountName: 'WhatsApp Business', accountIdentifier: '+44 20 7946 0123', lastSyncAt: '2025-06-18T12:00:00Z' },
  { provider: 'google_reviews', connected: true, accountName: 'Google Business', accountIdentifier: 'Mikes Plumbing', lastSyncAt: '2025-06-20T06:00:00Z' },
];

export function Settings() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: tenant, isLoading, error } = useSettings();
  const { data: featureFlags } = useFeatureFlags();
  // External integrations (accounting sync, WhatsApp, Twilio, …) are not yet
  // implemented; the tab stays hidden until the `external_integrations`
  // feature flag is enabled in Railway.
  const externalIntegrationsEnabled = featureFlags?.externalIntegrations === true;
  const visibleTabs = externalIntegrationsEnabled ? tabs : tabs.filter(tab => tab.id !== 'integrations');
  const updateSettings = useUpdateSettings();
  const [activeTab, setActiveTab] = useState('business');
  const [localServices, setLocalServices] = useState<ServiceOffering[]>(initialServices);
  const [localIntegrations, setLocalIntegrations] = useState<IntegrationStatus[]>(initialIntegrations);

  useEffect(() => {
    setPageTitle('Settings');
  }, [setPageTitle]);

  const handleSaveBusiness = (data: Partial<Tenant>) => {
    updateSettings.mutate(data, {
      onSuccess: () => toast.success('Business settings saved'),
      onError: (err) => toast.error(err.message || 'Failed to save settings'),
    });
  };

  const handleSaveBranding = (data: Partial<Tenant>) => {
    updateSettings.mutate(data, {
      onSuccess: () => toast.success('Branding settings saved'),
      onError: (err) => toast.error(err.message || 'Failed to save settings'),
    });
  };

  const handleSaveServices = () => {
    updateSettings.mutate(
      { services: localServices, integrations: localIntegrations } as Partial<Tenant>,
      {
        onSuccess: () => toast.success('Services saved'),
        onError: (err) => toast.error(err.message || 'Failed to save services'),
      }
    );
  };

  const handleSaveIntegrations = () => {
    updateSettings.mutate(
      { integrations: localIntegrations, services: localServices } as Partial<Tenant>,
      {
        onSuccess: () => toast.success('Integrations saved'),
        onError: (err) => toast.error(err.message || 'Failed to save integrations'),
      }
    );
  };

  if (isLoading || !tenant) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load settings</div>;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-[#1C1917]">Settings</h2>

      <div className="flex gap-6">
        {/* Settings nav */}
        <div className="w-40 flex-shrink-0 space-y-0.5">
          {visibleTabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-2 h-10 px-3 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.id ? 'bg-[#FFF7ED] text-[#D4650A]' : 'text-[#57534E] hover:bg-[#F5F4F0]'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {activeTab === 'business' && (
            <BusinessTab tenant={tenant} onSave={handleSaveBusiness} isSubmitting={updateSettings.isPending} />
          )}

          {activeTab === 'branding' && (
            <BrandingTab tenant={tenant} onSave={handleSaveBranding} isSubmitting={updateSettings.isPending} />
          )}

          {activeTab === 'services' && (
            <ServicesTab services={localServices} onChange={setLocalServices} onSave={handleSaveServices} isSubmitting={updateSettings.isPending} />
          )}

          {activeTab === 'integrations' && externalIntegrationsEnabled && (
            <IntegrationsTab integrations={localIntegrations} onChange={setLocalIntegrations} onSave={handleSaveIntegrations} isSubmitting={updateSettings.isPending} />
          )}
        </div>
      </div>
    </div>
  );
}

function BusinessTab({ tenant, onSave, isSubmitting }: Readonly<{ tenant: Tenant; onSave: (data: Partial<Tenant>) => void; isSubmitting: boolean }>) {
  const [name, setName] = useState(tenant.name);
  const [email, setEmail] = useState(tenant.email);
  const [phone, setPhone] = useState(tenant.phone);
  const [website, setWebsite] = useState(tenant.website ?? '');
  const [address, setAddress] = useState(tenant.address);
  const [hourlyLaborRate, setHourlyLaborRate] = useState(tenant.hourlyLaborRate);
  const [dailyLaborRate, setDailyLaborRate] = useState(tenant.dailyLaborRate ?? 0);
  const [mateDailyRate, setMateDailyRate] = useState(tenant.mateDailyRate ?? 0);
  const [matePercent, setMatePercent] = useState(tenant.matePercent ?? 55);
  const [markupPercentage, setMarkupPercentage] = useState(tenant.markupPercentage);
  const [minMarginPercent, setMinMarginPercent] = useState(tenant.minMarginPercent ?? 0);
  const [priceTolerancePercent, setPriceTolerancePercent] = useState(tenant.priceTolerancePercent ?? 15);
  const [minimumCharge, setMinimumCharge] = useState(tenant.minimumCharge);
  const [vatRate, setVatRate] = useState(tenant.vatRate);

  const numericRules = {
    hourlyLaborRate: { label: 'Hourly Rate', min: 0, max: 1000 },
    dailyLaborRate: { label: 'Daily Rate', min: 0, max: 5000 },
    mateDailyRate: { label: 'Mate Daily Rate', min: 0, max: 5000 },
    matePercent: { label: 'Mate % of Electrician', min: 0, max: 100 },
    markupPercentage: { label: 'Markup', min: 0, max: 100 },
    minMarginPercent: { label: 'Minimum Margin', min: 0, max: 100 },
    priceTolerancePercent: { label: 'Price Tolerance', min: 0, max: 100 },
    minimumCharge: { label: 'Minimum Charge', min: 0, max: 10000 },
    vatRate: { label: 'VAT Rate', min: 0, max: 100 },
  } as const;

  const numericValues = {
    hourlyLaborRate,
    dailyLaborRate,
    mateDailyRate,
    matePercent,
    markupPercentage,
    minMarginPercent,
    priceTolerancePercent,
    minimumCharge,
    vatRate,
  } as const;

  const pricingErrors = Object.entries(numericRules)
    .map(([field, rule]) => {
      const value = numericValues[field as keyof typeof numericValues];
      if (!Number.isFinite(value)) {
        return `${rule.label} must be a valid number.`;
      }
      if (value < rule.min || value > rule.max) {
        return `${rule.label} must be between ${rule.min} and ${rule.max}.`;
      }
      return null;
    })
    .filter((message): message is string => message !== null);

  const saveDisabled = isSubmitting || pricingErrors.length > 0;

  const parseNumericInput = (value: string): number => {
    if (value.trim() === '') {
      return Number.NaN;
    }
    return Number(value);
  };

  const numericInputValue = (value: number): string => (Number.isFinite(value) ? value.toString() : '');

  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] p-6 shadow-sm space-y-4 max-w-xl">
      <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em]">Business Details</h3>
      <div className="grid grid-cols-2 gap-4">
        <FormField label="Business Name" value={name} onChange={setName} />
        <FormField label="Email" value={email} onChange={setEmail} />
        <FormField label="Phone" value={phone} onChange={setPhone} />
        <FormField label="Website" value={website} onChange={setWebsite} />
        <FormField label="Address" value={address} onChange={setAddress} className="col-span-2" />
      </div>
      <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em] pt-4 border-t border-[#F0EFEA]">Pricing</h3>
      <div className="grid grid-cols-2 gap-4">
        <FormField label="Hourly Rate (£)" value={numericInputValue(hourlyLaborRate)} onChange={v => setHourlyLaborRate(parseNumericInput(v))} type="number" min={0} max={1000} step="0.01" />
        <FormField label="Daily Rate (£)" value={numericInputValue(dailyLaborRate)} onChange={v => setDailyLaborRate(parseNumericInput(v))} type="number" min={0} max={5000} step="0.01" />
        <FormField label="Mate Daily Rate (£)" value={numericInputValue(mateDailyRate)} onChange={v => setMateDailyRate(parseNumericInput(v))} type="number" min={0} max={5000} step="0.01" />
        <FormField label="Mate % of Electrician" value={numericInputValue(matePercent)} onChange={v => setMatePercent(parseNumericInput(v))} type="number" min={0} max={100} step="0.01" />
        <FormField label="Markup (%)" value={numericInputValue(markupPercentage)} onChange={v => setMarkupPercentage(parseNumericInput(v))} type="number" min={0} max={100} step="0.01" />
        <FormField label="Minimum Margin (%)" value={numericInputValue(minMarginPercent)} onChange={v => setMinMarginPercent(parseNumericInput(v))} type="number" min={0} max={100} step="0.01" />
        <FormField label="Price Tolerance (%)" value={numericInputValue(priceTolerancePercent)} onChange={v => setPriceTolerancePercent(parseNumericInput(v))} type="number" min={0} max={100} step="0.01" />
        <FormField label="Minimum Charge (£)" value={numericInputValue(minimumCharge)} onChange={v => setMinimumCharge(parseNumericInput(v))} type="number" min={0} max={10000} step="0.01" />
        <FormField label="VAT Rate (%)" value={numericInputValue(vatRate)} onChange={v => setVatRate(parseNumericInput(v))} type="number" min={0} max={100} step="0.01" />
      </div>
      {pricingErrors.length > 0 && (
        <div className="rounded-lg border border-[#FECACA] bg-[#FEF2F2] px-3 py-2">
          <p className="text-xs font-semibold text-[#991B1B]">Fix pricing fields before saving:</p>
          <ul className="mt-1 list-disc pl-4 text-xs text-[#B91C1C]">
            {pricingErrors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="pt-4 border-t border-[#F0EFEA] flex justify-end">
        <button
          disabled={saveDisabled}
          onClick={() => onSave({
            name,
            email,
            phone,
            website: website || null,
            address,
            hourlyLaborRate,
            dailyLaborRate,
            mateDailyRate,
            matePercent,
            markupPercentage,
            minMarginPercent,
            priceTolerancePercent,
            minimumCharge,
            vatRate,
          })}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save className="w-4 h-4" /> {isSubmitting ? 'Saving...' : 'Save Business'}
        </button>
      </div>
    </div>
  );
}

function BrandingTab({ tenant, onSave, isSubmitting }: Readonly<{ tenant: Tenant; onSave: (data: Partial<Tenant>) => void; isSubmitting: boolean }>) {
  const [primaryColor, setPrimaryColor] = useState(tenant.primaryColor);
  const [secondaryColor, setSecondaryColor] = useState(tenant.secondaryColor);
  const [logoUrl, setLogoUrl] = useState(tenant.logoUrl ?? '');

  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] p-6 shadow-sm max-w-xl">
      <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em] mb-4">Branding</h3>
      <div className="border-2 border-dashed border-[#E7E5E4] rounded-lg p-8 text-center hover:border-[#D4650A] transition-colors cursor-pointer">
        <img src={logoUrl || '/logo-icon.jpg'} alt="Logo" className="w-16 h-16 mx-auto mb-3 rounded-lg object-cover" />
        <div className="text-sm font-medium text-[#1C1917]">Click to upload logo</div>
        <div className="text-xs text-[#78716C] mt-1">PNG, JPG up to 2MB</div>
      </div>
      <div className="grid grid-cols-1 gap-4 mt-4">
        <FormField label="Logo URL" value={logoUrl} onChange={setLogoUrl} />
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Primary Color" value={primaryColor} onChange={setPrimaryColor} />
          <FormField label="Secondary Color" value={secondaryColor} onChange={setSecondaryColor} />
        </div>
      </div>
      <div className="pt-4 border-t border-[#F0EFEA] flex justify-end mt-4">
        <button
          disabled={isSubmitting}
          onClick={() => onSave({ primaryColor, secondaryColor, logoUrl: logoUrl || null })}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {isSubmitting ? 'Saving...' : 'Save Branding'}
        </button>
      </div>
    </div>
  );
}

function ServicesTab({
  services,
  onChange,
  onSave,
  isSubmitting,
}: Readonly<{
  services: ServiceOffering[];
  onChange: (services: ServiceOffering[]) => void;
  onSave: () => void;
  isSubmitting: boolean;
}>) {
  const [isAdding, setIsAdding] = useState(false);
  const [newService, setNewService] = useState({ name: '', description: '', basePrice: '', estimatedDuration: '', category: '', isActive: true });

  const toggleActive = (id: string) => {
    onChange(services.map(s => s.id === id ? { ...s, isActive: !s.isActive } : s));
  };

  const addService = () => {
    if (!newService.name) return;
    onChange([
      ...services,
      {
        id: `svc-${Date.now()}`,
        name: newService.name,
        description: newService.description || null,
        basePrice: newService.basePrice ? Number(newService.basePrice) : null,
        estimatedDuration: newService.estimatedDuration ? Number(newService.estimatedDuration) : null,
        category: newService.category,
        isActive: newService.isActive,
      },
    ]);
    setNewService({ name: '', description: '', basePrice: '', estimatedDuration: '', category: '', isActive: true });
    setIsAdding(false);
  };

  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-[#F0EFEA] flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em]">Services</h3>
        <button onClick={() => setIsAdding(true)} className="h-8 px-3 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Add Service</button>
      </div>
      <div className="divide-y divide-[#F0EFEA]">
        {services.map(svc => (
          <div key={svc.id} className="px-6 py-4 flex items-center justify-between hover:bg-[#F5F4F0] transition-colors">
            <div>
              <div className="flex items-center gap-2">
                <button onClick={() => toggleActive(svc.id)} className={`w-2 h-2 rounded-full ${svc.isActive ? 'bg-[#16A34A]' : 'bg-[#A8A29E]'}`} />
                <span className="text-sm font-medium text-[#1C1917]">{svc.name}</span>
              </div>
              {svc.description && <div className="text-xs text-[#78716C] mt-0.5 ml-4">{svc.description}</div>}
            </div>
            <div className="flex items-center gap-4 text-xs text-[#78716C]">
              {svc.basePrice && <span>£{svc.basePrice}</span>}
              {svc.estimatedDuration && <span>{svc.estimatedDuration}min</span>}
              <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-[11px]">{svc.category}</span>
            </div>
          </div>
        ))}
      </div>
      {isAdding && (
        <div className="px-6 py-4 bg-[#F5F4F0] space-y-2">
          <input placeholder="Name" value={newService.name} onChange={e => setNewService({ ...newService, name: e.target.value })} className="w-full h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg" />
          <input placeholder="Description" value={newService.description} onChange={e => setNewService({ ...newService, description: e.target.value })} className="w-full h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg" />
          <div className="grid grid-cols-3 gap-2">
            <input placeholder="Price" value={newService.basePrice} onChange={e => setNewService({ ...newService, basePrice: e.target.value })} className="h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg" />
            <input placeholder="Duration (min)" value={newService.estimatedDuration} onChange={e => setNewService({ ...newService, estimatedDuration: e.target.value })} className="h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg" />
            <input placeholder="Category" value={newService.category} onChange={e => setNewService({ ...newService, category: e.target.value })} className="h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg" />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setIsAdding(false)} className="h-8 px-3 text-xs text-[#57534E]">Cancel</button>
            <button onClick={addService} className="h-8 px-3 rounded-lg bg-[#D4650A] text-white text-xs font-semibold">Add</button>
          </div>
        </div>
      )}
      <div className="px-6 py-4 border-t border-[#F0EFEA] flex justify-end">
        <button
          disabled={isSubmitting}
          onClick={onSave}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {isSubmitting ? 'Saving...' : 'Save Services'}
        </button>
      </div>
    </div>
  );
}

function IntegrationsTab({
  integrations,
  onChange,
  onSave,
  isSubmitting,
}: Readonly<{
  integrations: IntegrationStatus[];
  onChange: (integrations: IntegrationStatus[]) => void;
  onSave: () => void;
  isSubmitting: boolean;
}>) {
  const toggle = (provider: IntegrationStatus['provider']) => {
    onChange(integrations.map(int => int.provider === provider ? { ...int, connected: !int.connected, lastSyncAt: int.connected ? null : new Date().toISOString() } : int));
  };

  return (
    <div className="space-y-3">
      {integrations.map((int) => (
        <div key={int.provider} className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${int.connected ? 'bg-[#F0FDF4]' : 'bg-[#F5F4F0]'}`}>
              {int.connected ? <CheckCircle className="w-5 h-5 text-[#16A34A]" /> : <XCircle className="w-5 h-5 text-[#A8A29E]" />}
            </div>
            <div>
              <div className="text-sm font-semibold text-[#1C1917] capitalize">{int.provider.replace('_', ' ')}</div>
              <div className="text-xs text-[#78716C]">
                {int.connected ? int.accountIdentifier || 'Connected' : 'Not connected'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {int.connected && int.lastSyncAt && (
              <span className="text-[11px] text-[#78716C]">
                Synced {new Date(int.lastSyncAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
            <button
              onClick={() => toggle(int.provider)}
              className={`h-8 px-3 rounded-lg text-xs font-semibold transition-colors ${
                int.connected
                  ? 'bg-[#F5F4F0] text-[#57534E] hover:bg-[#EFEEE9]'
                  : 'bg-[#D4650A] text-white hover:bg-[#B85500]'
              }`}
            >
              {int.connected ? 'Disconnect' : 'Connect'}
            </button>
            {int.connected && (
              <button className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-[#F5F4F0] transition-colors">
                <RefreshCw className="w-4 h-4 text-[#78716C]" />
              </button>
            )}
          </div>
        </div>
      ))}
      <div className="flex justify-end pt-2">
        <button
          disabled={isSubmitting}
          onClick={onSave}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {isSubmitting ? 'Saving...' : 'Save Integrations'}
        </button>
      </div>
    </div>
  );
}

function FormField({ label, value, onChange, className = '', type = 'text', min, max, step }: Readonly<{ label: string; value: string | number; onChange: (value: string) => void; className?: string; type?: 'text' | 'number'; min?: number; max?: number; step?: string }>) {
  return (
    <div className={className}>
      <label className="block text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-1">{label}</label>
      <input
        type={type}
        value={value}
        aria-label={label}
        inputMode={type === 'number' ? 'decimal' : undefined}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(e.target.value)}
        className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] focus:ring-2 focus:ring-[#FFF7ED] transition-all"
      />
    </div>
  );
}
