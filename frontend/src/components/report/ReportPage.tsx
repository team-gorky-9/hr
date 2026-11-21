import React, { useState } from 'react';
import ReportShell, { ReportTab } from './ReportShell';
import Overview from './Overview';
import Dynamics from './Dynamics';
import Builder from './Builder';
import Staff from './Staff';
import Coverage from './Coverage';
import { Toast } from '../shared/ui';

/** Годовой кадровый доклад (макеты годовой-доклад 1–10). Данные — заглушки, см. STUBS.md. */
export const ReportPage: React.FC = () => {
  const [tab, setTab] = useState<ReportTab>('overview');
  const [toast, setToast] = useState<string | null>(null);
  const notify = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 3000);
  };
  return (
    <>
      <ReportShell tab={tab} onTab={setTab} onDownload={() => notify('Годовой XLSX: заглушка скачивания')}>
        {tab === 'overview' && (
          <Overview onOpenBuilder={() => setTab('builder')} onDownloadSlice={() => notify('Срез: заглушка скачивания')} />
        )}
        {tab === 'dynamics' && <Dynamics />}
        {tab === 'builder' && <Builder />}
        {tab === 'staff' && <Staff onDownload={() => notify('Excel по подразделениям: заглушка скачивания')} />}
        {tab === 'coverage' && <Coverage onNotify={notify} />}
      </ReportShell>
      <Toast message={toast} />
    </>
  );
};

export default ReportPage;
