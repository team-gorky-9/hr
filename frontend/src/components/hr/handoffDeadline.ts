export const RESPONSE_WORKING_DAYS = 10;
export const REMINDER_WORKING_DAY = 7;

// Snapshot of app/db/seed.py:PRODUCTION_CALENDAR_DAYS for this demo screen.
// Real API handoffs use the server calendar, including administrator overrides.
const holidays = new Set([
  '2025-02-23', '2025-03-08', '2025-05-01', '2025-05-02', '2025-05-08',
  '2025-05-09', '2025-06-12', '2025-06-13', '2025-11-03', '2025-11-04', '2025-12-31',
  '2026-01-09', '2026-02-23', '2026-03-08', '2026-03-09', '2026-05-01',
  '2026-05-09', '2026-05-11', '2026-06-12', '2026-11-04', '2026-12-31',
  '2027-02-23', '2027-03-08', '2027-05-01', '2027-05-03', '2027-05-09',
  '2027-05-10', '2027-06-12', '2027-06-14', '2027-11-04',
]);
for (const year of [2025, 2026, 2027]) {
  for (let day = 1; day <= 8; day++) holidays.add(`${year}-01-0${day}`);
}

export function moscowDay(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

export function isDateOnly(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function workingDay(date: Date): boolean {
  const day = date.toISOString().slice(0, 10);
  if (day === '2025-11-01') return true;
  return !holidays.has(day) && date.getUTCDay() !== 0 && date.getUTCDay() !== 6;
}

export function addWorkingDays(start: string, count: number): string {
  const date = new Date(`${start}T00:00:00Z`);
  for (let left = Math.abs(count); left > 0;) {
    date.setUTCDate(date.getUTCDate() + Math.sign(count));
    if (workingDay(date)) left--;
  }
  return date.toISOString().slice(0, 10);
}

function workingDaysBetween(start: string, end: string): number {
  const date = new Date(`${start}T00:00:00Z`);
  let days = 0;
  while (date.toISOString().slice(0, 10) < end) {
    date.setUTCDate(date.getUTCDate() + 1);
    if (workingDay(date)) days++;
  }
  return days;
}

export function deadlineProgress(sentOn: string, dueOn: string, today: string) {
  const total = Math.max(1, workingDaysBetween(sentOn, dueOn));
  const elapsed = workingDaysBetween(sentOn, today);
  const reminderOn = addWorkingDays(dueOn, -(RESPONSE_WORKING_DAYS - REMINDER_WORKING_DAY));
  const status: 'on_track' | 'due_soon' | 'overdue' = today > dueOn ? 'overdue' : today >= reminderOn ? 'due_soon' : 'on_track';
  return { elapsed, total, percent: Math.min(100, Math.max(0, elapsed / total * 100)), status };
}

export function displayDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('ru-RU', { timeZone: 'UTC' });
}
