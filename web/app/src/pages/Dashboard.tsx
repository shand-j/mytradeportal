import { useEffect } from 'react';
import { TrendingUp, TrendingDown, FileText, Wrench, Star, Clock, Phone, Sparkles } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { useDashboard } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { formatDistanceToNow } from 'date-fns';

export function Dashboard() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data, isLoading, error } = useDashboard();

  useEffect(() => {
    setPageTitle('Dashboard');
  }, [setPageTitle]);

  if (isLoading || !data?.kpi) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return <div className="text-center py-12 text-[#DC2626]">Failed to load dashboard</div>;
  }

  const { kpi, revenueChart, serviceBreakdown, recentActivity } = data;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Revenue This Month"
          value={`£${kpi.revenueThisMonth.toLocaleString()}`}
          change={`${kpi.revenueChange > 0 ? '+' : ''}${kpi.revenueChange}% vs last month`}
          changePositive={kpi.revenueChange > 0}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <KpiCard
          label="Active Jobs"
          value={kpi.activeJobs.toString()}
          change={`${kpi.jobsCapacity - kpi.activeJobs} slots remaining`}
          changePositive={true}
          icon={<Wrench className="w-4 h-4" />}
          progress={kpi.activeJobs / kpi.jobsCapacity}
        />
        <KpiCard
          label="Pending Quotes"
          value={kpi.pendingQuotes.toString()}
          change={`£${(kpi.pendingQuotesValue / 1000).toFixed(0)}k total value`}
          changePositive={true}
          icon={<FileText className="w-4 h-4" />}
          warning={kpi.quotesExpiringSoon > 0 ? `${kpi.quotesExpiringSoon} expire this week` : undefined}
        />
        <KpiCard
          label="Customer Rating"
          value={kpi.averageRating.toString()}
          change={`${kpi.reviewCount} reviews`}
          changePositive={true}
          icon={<Star className="w-4 h-4" />}
          stars={kpi.averageRating}
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Revenue Chart */}
        <div className="lg:col-span-3 bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[#1C1917]">Revenue Overview</h2>
            <div className="flex gap-1">
              {['Week', 'Month', 'Year'].map(p => (
                <button key={p} className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  p === 'Month' ? 'bg-[#1C1917] text-white' : 'text-[#57534E] hover:bg-[#F5F4F0]'
                }`}>
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={revenueChart.labels.map((l, i) => ({
                label: l,
                revenue: revenueChart.revenue[i],
                target: revenueChart.target[i],
              }))}>
                <defs>
                  <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#D4650A" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#D4650A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0EFEA" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} tickFormatter={(v) => `£${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: 'white', border: '1px solid #E7E5E4', borderRadius: '8px', boxShadow: '0 4px 12px rgba(28,25,23,0.08)' }}
                  formatter={(value: number) => [`£${value.toLocaleString()}`, 'Revenue']}
                />
                <Area type="monotone" dataKey="revenue" stroke="#D4650A" strokeWidth={2} fill="url(#revGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Service Breakdown */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-[#1C1917] mb-4">Service Mix</h2>
          <div className="h-[200px] flex items-center justify-center relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={serviceBreakdown || []}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={85}
                  dataKey="percentage"
                  nameKey="service"
                  strokeWidth={0}
                >
                  {(serviceBreakdown || []).map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute flex flex-col items-center">
              <span className="text-xl font-bold text-[#1C1917]">£{(kpi.revenueThisMonth / 1000).toFixed(1)}k</span>
              <span className="text-xs text-[#78716C]">Total</span>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            {(serviceBreakdown || []).map(s => (
              <div key={s.service} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
                <span className="text-sm text-[#1C1917] flex-1">{s.service}</span>
                <span className="text-sm font-medium text-[#57534E]">{s.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Activity Feed */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-[#1C1917]">Recent Activity</h2>
          <button className="text-xs font-medium text-[#D4650A] hover:underline">View all</button>
        </div>
        <div className="space-y-1">
          {recentActivity.map(act => (
            <div key={act.id} className="flex items-center gap-3 py-3 border-b border-[#F0EFEA] last:border-0">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${
                act.type.includes('voice') ? 'bg-[#F5F3FF]' :
                act.type.includes('quote_accepted') ? 'bg-[#F0FDF4]' :
                act.type.includes('invoice_paid') ? 'bg-[#F0FDF4]' :
                act.type.includes('ai') ? 'bg-[#F5F3FF]' :
                act.type.includes('job') ? 'bg-[#EFF6FF]' :
                'bg-[#FFF7ED]'
              }`}>
                {act.type.includes('voice') ? <Phone className="w-4 h-4 text-[#7C3AED]" /> :
                 act.type.includes('quote') ? <FileText className="w-4 h-4 text-[#D4650A]" /> :
                 act.type.includes('invoice') ? <FileText className="w-4 h-4 text-[#16A34A]" /> :
                 act.type.includes('job') ? <Wrench className="w-4 h-4 text-[#2563EB]" /> :
                 act.type.includes('ai') ? <Sparkles className="w-4 h-4 text-[#7C3AED]" /> :
                 <Clock className="w-4 h-4 text-[#D4650A]" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-[#1C1917] truncate">{act.title}</div>
                {act.description && <div className="text-xs text-[#78716C] truncate">{act.description}</div>}
              </div>
              <div className="text-xs text-[#A8A29E] flex-shrink-0">
                {formatDistanceToNow(new Date(act.createdAt), { addSuffix: true })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ label, value, change, changePositive, icon, progress, warning, stars }: {
  label: string; value: string; change: string; changePositive: boolean;
  icon: React.ReactNode; progress?: number; warning?: string; stars?: number;
}) {
  return (
    <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">{label}</span>
        <span className={`${changePositive ? 'text-[#16A34A]' : 'text-[#DC2626]'}`}>{icon}</span>
      </div>
      <div className="text-2xl font-bold text-[#1C1917] mb-1">{value}</div>
      <div className="flex items-center gap-1.5">
        {changePositive ? <TrendingUp className="w-3 h-3 text-[#16A34A]" /> : <TrendingDown className="w-3 h-3 text-[#DC2626]" />}
        <span className={`text-xs ${changePositive ? 'text-[#16A34A]' : 'text-[#DC2626]'}`}>{change}</span>
      </div>
      {progress !== undefined && (
        <div className="mt-3 h-1.5 bg-[#DCFCE7] rounded-full overflow-hidden">
          <div className="h-full bg-[#16A34A] rounded-full transition-all" style={{ width: `${progress * 100}%` }} />
        </div>
      )}
      {warning && <div className="mt-2 text-[11px] text-[#DC2626]">{warning}</div>}
      {stars && (
        <div className="flex gap-0.5 mt-2">
          {[1, 2, 3, 4, 5].map(s => (
            <Star key={s} className={`w-4 h-4 ${s <= Math.floor(stars) ? 'text-amber-400 fill-amber-400' : s - 0.5 <= stars ? 'text-amber-400 fill-amber-400/50' : 'text-[#E7E5E4]'}`} />
          ))}
        </div>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="bg-[#1C1917] rounded-xl h-16 animate-pulse" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-white rounded-xl border border-[#E7E5E4] p-5 animate-pulse">
            <div className="h-3 bg-[#F5F4F0] rounded w-24 mb-3" />
            <div className="h-8 bg-[#F5F4F0] rounded w-20 mb-2" />
            <div className="h-3 bg-[#F5F4F0] rounded w-32" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 bg-white rounded-xl border border-[#E7E5E4] p-5 h-[380px] animate-pulse" />
        <div className="lg:col-span-2 bg-white rounded-xl border border-[#E7E5E4] p-5 h-[380px] animate-pulse" />
      </div>
    </div>
  );
}
