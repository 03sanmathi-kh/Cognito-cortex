export interface DashboardKpi {
  id: string
  label: string
  value: number
  prefix?: string
  suffix?: string
  displayFormat?: (val: number) => string
  trend: {
    value: number | string
    isPositive: boolean
    variant?: 'auto' | 'green' | 'red' | 'purple' | 'neutral'
  }
  caption: string
  iconName: string
  iconColor: 'magenta' | 'purple' | 'green' | 'blue' | 'amber'
}

export interface RevenuePoint extends Record<string, unknown> {
  period: string
  thisQuarter: number
  previousQuarter: number
}

export interface SuggestedAction {
  id: string
  title: string
  prompt: string
  description: string
  lastRun: string
  iconName: string
  accentColor: 'magenta' | 'purple' | 'green'
}

export interface RecentPageItem {
  id: string
  name: string
  path: string
  status: 'published' | 'draft' | 'warning' | 'success' | 'danger'
  targetAttainment: number
  variant: 'magenta' | 'purple' | 'green' | 'blue' | 'gradient'
  lastVisited: string
  iconName: string
}

export interface PinnedDashboardItem {
  id: string
  title: string
  caption: string
  progress: number
  color: string
  iconName: string
}

export const mockDashboardData = {
  kpis: [
    {
      id: 'revenue',
      label: 'Revenue',
      value: 2840000,
      prefix: '$',
      displayFormat: () => '2.84M',
      trend: {
        value: 8.7,
        isPositive: true,
        variant: 'purple',
      },
      caption: 'vs previous quarter',
      iconName: 'DollarSign',
      iconColor: 'magenta',
    },
    {
      id: 'orders',
      label: 'Orders',
      value: 18420,
      trend: {
        value: 5.3,
        isPositive: true,
        variant: 'green',
      },
      caption: 'vs previous quarter',
      iconName: 'ShoppingBag',
      iconColor: 'purple',
    },
    {
      id: 'avg-order-value',
      label: 'Avg. Order Value',
      value: 154,
      prefix: '$',
      trend: {
        value: -1.2,
        isPositive: false,
        variant: 'red',
      },
      caption: 'vs previous quarter',
      iconName: 'Receipt',
      iconColor: 'purple',
    },
    {
      id: 'active-customers',
      label: 'Active Customers',
      value: 6310,
      trend: {
        value: 3.9,
        isPositive: true,
        variant: 'green',
      },
      caption: 'vs previous quarter',
      iconName: 'Users',
      iconColor: 'purple',
    },
  ] as DashboardKpi[],

  revenueTrend: [
    { period: 'W1', thisQuarter: 175, previousQuarter: 130 },
    { period: 'W2', thisQuarter: 195, previousQuarter: 145 },
    { period: 'W3', thisQuarter: 230, previousQuarter: 160 },
    { period: 'W4', thisQuarter: 210, previousQuarter: 185 },
    { period: 'W5', thisQuarter: 260, previousQuarter: 170 },
    { period: 'W6', thisQuarter: 245, previousQuarter: 205 },
    { period: 'W7', thisQuarter: 290, previousQuarter: 190 },
    { period: 'W8', thisQuarter: 320, previousQuarter: 215 },
    { period: 'W9', thisQuarter: 280, previousQuarter: 240 },
    { period: 'W10', thisQuarter: 350, previousQuarter: 220 },
    { period: 'W11', thisQuarter: 385, previousQuarter: 260 },
    { period: 'W12', thisQuarter: 410, previousQuarter: 275 },
  ] as RevenuePoint[],

  suggestedActions: [
    {
      id: 'action-1',
      title: 'Compare this quarter',
      prompt: 'Compare Q3 revenue and fulfillment speed vs Q2 across all 4 distribution regions.',
      description: 'Benchmark North, South, East & West revenue against Q2 targets.',
      lastRun: 'Today at 09:40 am',
      iconName: 'TrendingUp',
      accentColor: 'magenta',
    },
    {
      id: 'action-2',
      title: 'Why did South drop?',
      prompt: 'Identify likely causes for the 14% revenue dip in Meridian South distribution center.',
      description: 'Inspect margin contraction, regional delayed shipments, and customer churn.',
      lastRun: 'Yesterday at 04:15 pm',
      iconName: 'AlertCircle',
      accentColor: 'green',
    },
    {
      id: 'action-3',
      title: 'Top reorder bottlenecks',
      prompt: 'Find SKUs currently beneath reorder threshold across East and West warehouses.',
      description: 'List 12 critical inventory SKUs with stockout risk in the next 14 days.',
      lastRun: '2 Oct, 08:30 am',
      iconName: 'Boxes',
      accentColor: 'purple',
    },
  ] as SuggestedAction[],

  recentPages: [
    {
      id: 'page-1',
      name: 'Revenue by Region',
      path: '/finance/revenue',
      status: 'published',
      targetAttainment: 82,
      variant: 'purple',
      lastVisited: '12 mins ago',
      iconName: 'BarChart2',
    },
    {
      id: 'page-2',
      name: 'Inventory Health',
      path: '/inventory/stock',
      status: 'warning',
      targetAttainment: 64,
      variant: 'green',
      lastVisited: '1 hour ago',
      iconName: 'Boxes',
    },
    {
      id: 'page-3',
      name: 'Regional Targets',
      path: '/sales/pipeline',
      status: 'success',
      targetAttainment: 91,
      variant: 'gradient',
      lastVisited: '3 hours ago',
      iconName: 'Target',
    },
  ] as RecentPageItem[],

  pinnedDashboards: [
    {
      id: 'pinned-1',
      title: 'Supply Chain Velocity',
      caption: 'Multi-region transit & freight transit KPIs',
      progress: 78,
      color: '#D946EF',
      iconName: 'Truck',
    },
    {
      id: 'pinned-2',
      title: 'Executive Financial Summary',
      caption: 'Operating margins, gross profit & cash flow',
      progress: 92,
      color: '#22C55E',
      iconName: 'PieChart',
    },
  ] as PinnedDashboardItem[],
}
