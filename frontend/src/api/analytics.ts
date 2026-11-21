import { contour, request } from './archive';
import { annualReportsPath, downloadWorkbook } from './reports';

export type Period = { from: string; to: string };
type Count = { code: string; title: string; count: number };
export type Dashboard = {
  as_of: string;
  period_from: string;
  period_to: string;
  totals: { received: number; screened: number; interviews: number; hired: number; forwarded: number };
  weeks: { start: string; end: string; screened: number; interviews: number }[];
  stages: Count[];
  sources: { channel: string; count: number }[];
  rejections: Count[];
  vacancies: {
    id: string; title: string; received: number; interviews: number; forwarded: number; days_open: number | null;
    waiting: number; due_soon: number; overdue: number;
  }[];
};

export type ReportVersion = { snapshot_id: string; year: number; extracted_at: string };
type ReportMetric = { value: number | null; status: string };
type Metrics = Record<string, ReportMetric>;
export type ReportSlice = { totals: Metrics; rows: { dimensions: { month?: string | number }; metrics: Metrics }[] };
export type ReportQuery = { start_month: number; end_month: number; metrics: string[]; group_by: ['month']; compare_previous: boolean };

export const analyticsApi = {
  dashboard: ({ from, to }: Period, vacancy: string, signal: AbortSignal) => {
    const params = new URLSearchParams({ period_from: from, period_to: to, contour });
    if (vacancy) params.set('vacancy_id', vacancy);
    return request<Dashboard>('/analytics/dashboard?' + params, { signal });
  },
  vacancies: (signal: AbortSignal) => request<{ items: { vacancy_id: string; title: string }[] }>(`/vacancies?contour=${contour}`, { signal }),
  versions: (signal?: AbortSignal) => request<ReportVersion[]>(annualReportsPath, { signal }),
  report: (id: string, query: ReportQuery) => request<ReportSlice>(`${annualReportsPath}/${id}/query`, { method: 'POST', body: JSON.stringify(query) }),
  downloadAnnual: (id: string) => downloadWorkbook(id, '/xlsx'),
  downloadReport: (id: string, query: ReportQuery) => downloadWorkbook(id, '/query/xlsx', query),
};
