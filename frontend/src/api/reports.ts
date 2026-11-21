import { archiveApiBase } from './archive';

export const annualReportsPath = '/reports/annual';

const workbookType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

export async function downloadWorkbook(
  snapshotId: string,
  suffix: '/xlsx' | '/query/xlsx' | '/operations/xlsx',
  body?: Record<string, unknown>,
) {
  const response = await fetch(`${archiveApiBase}${annualReportsPath}/${snapshotId}${suffix}`, {
    method: body ? 'POST' : 'GET',
    credentials: 'same-origin',
    headers: {
      Accept: workbookType,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const contentType = response.headers.get('Content-Type')?.split(';')[0].trim();
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new Error(failure?.error?.message || `Не удалось скачать Excel (${response.status}).`);
  }
  if (contentType !== workbookType) throw new Error('Сервер не вернул файл Excel.');

  const workbook = await response.blob();
  const signature = new Uint8Array(await workbook.slice(0, 4).arrayBuffer());
  if (signature.join(',') !== '80,75,3,4') throw new Error('Полученный файл Excel повреждён.');

  const filename = response.headers.get('Content-Disposition')?.match(/filename="([a-z0-9-]+\.xlsx)"/i)?.[1];
  const url = URL.createObjectURL(workbook);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || `report-${snapshotId.slice(0, 12)}.xlsx`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
