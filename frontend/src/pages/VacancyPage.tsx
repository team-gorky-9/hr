import { useEffect, useRef, useState, type FormEvent } from 'react';
import { getPublicVacancy, type PublicVacancy } from '../api/publicVacancies';
import { hiringRequest, uploadBody, type CandidateRequest, type Document } from '../api/hiring';
import PersonalDataLawLinks from '../components/portal/PersonalDataLawLinks';

interface VacancyPageProps {
  vacancyId?: string;
  token?: string;
  onGoHome?: () => void;
  onGoCabinet?: (requestId?: string) => void;
  onLogin?: () => void;
}

const field = 'w-full px-3.5 bg-white border border-[#E1E5EB] rounded-lg text-[14px] text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]';
const primary = 'w-full h-11 bg-[#1F4FD1] hover:bg-[#1841B2] text-white font-medium text-[14px] rounded-lg transition-colors disabled:opacity-60';
const heading = 'text-[16px] font-bold text-[#141A24] mb-3';

function VacancyFactList({ items, compact = false }: { items: string[]; compact?: boolean }) {
  return <ul className={`space-y-2 text-[#334155] leading-relaxed ${compact ? 'text-[13px]' : 'text-[14px]'}`}>
    {items.map((item) => <li key={item} className="flex items-start gap-2">
      <span aria-hidden="true" className="text-[#141A24]">•</span>
      <span className="break-words min-w-0">{item}</span>
    </li>)}
  </ul>;
}

function VacancyFacts({ vacancy }: { vacancy: PublicVacancy }) {
  const { description, duties, duties_source, requirements, advertised_requirements, conditions } = vacancy;
  const training = vacancy.system === 'legacy';
  const mandatory = requirements?.filter((item) => item.mandatory).map((item) => item.text) ?? [];
  const optional = requirements?.filter((item) => !item.mandatory).map((item) => item.text) ?? [];

  return (
    <>
      {description && <p className="mb-8 whitespace-pre-wrap break-words text-[14px] text-[#334155] leading-relaxed">{description}</p>}
      {(training || !!duties?.length) && <section className="mb-8">
        <h2 className={heading}>Чем предстоит заниматься</h2>
        {duties_source && <p className="mb-3 text-[13px] text-[#616977]">{duties_source}</p>}
        {duties?.length ? <VacancyFactList items={duties} /> :
          <p className="text-[14px] text-[#616977]">Обязанности в доступных источниках не указаны.</p>}
      </section>}
      {!!advertised_requirements?.length && <section className="mb-4">
        <h2 className={heading}>Требования из объявления</h2>
        <VacancyFactList items={advertised_requirements} compact />
      </section>}
      {(training || !!requirements?.length) && <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <section className="bg-[#FFF6EC] border border-[#F3DDBF] rounded-xl p-5">
          <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Обязательные требования</h2>
          {mandatory.length ? <VacancyFactList items={mandatory} compact /> :
            <p className="text-[13px] text-[#616977]">В профиле не указаны.</p>}
        </section>
        <section className="bg-[#F7F8FA] border border-[#E1E5EB] rounded-xl p-5">
          <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Будет плюсом</h2>
          {optional.length ? <VacancyFactList items={optional} compact /> :
            <p className="text-[13px] text-[#616977]">В профиле не указано.</p>}
        </section>
      </div>}
      {(training || !!conditions?.length) && <section>
        <h2 className={heading}>Условия</h2>
        {conditions?.length ? <VacancyFactList items={conditions} /> :
          <p className="text-[14px] text-[#616977]">Условия работы в доступном объявлении не указаны.</p>}
      </section>}
    </>
  );
}

export function VacancyPage(props: VacancyPageProps) {
  return <VacancyDetails key={props.vacancyId} {...props} />;
}

function VacancyDetails({ vacancyId, token, onGoHome, onGoCabinet, onLogin }: VacancyPageProps) {
  const [vacancy, setVacancy] = useState<PublicVacancy | null>(null);
  const [loadError, setLoadError] = useState('');
  const [reload, setReload] = useState(0);
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [draftId, setDraftId] = useState<string>();
  const [submitted, setSubmitted] = useState<CandidateRequest>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const creation = useRef<{ body: string; key: string }>();
  const sending = useRef(false);

  useEffect(() => {
    if (!vacancyId) return;
    const controller = new AbortController();
    setLoadError('');
    getPublicVacancy(vacancyId, controller.signal)
      .then(setVacancy)
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setVacancy(null);
          setLoadError(failure instanceof Error ? failure.message : 'Не удалось открыть вакансию.');
        }
      });
    return () => controller.abort();
  }, [vacancyId, reload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || !vacancy || sending.current) return;
    setError('');
    if (!file?.size) {
      setError('Приложите непустой файл резюме.');
      return;
    }
    sending.current = true;
    setBusy(true);
    try {
      let request: CandidateRequest;
      if (draftId) {
        request = await hiringRequest<CandidateRequest>(token, '/candidate-requests/' + draftId);
      } else {
        const body = {
          vacancy_ref: { system: vacancy.system, id: vacancy.id, revision: vacancy.revision },
          message: message.trim(),
          contact: { channel: 'email', value: email.trim() },
        };
        const encoded = JSON.stringify(body);
        if (creation.current?.body !== encoded) creation.current = { body: encoded, key: crypto.randomUUID() };
        request = await hiringRequest<CandidateRequest>(token, '/candidate-requests', body, 'POST', creation.current.key);
        setDraftId(request.id);
      }

      if (request.status === 'draft') {
        const path = '/candidate-requests/' + request.id;
        const possibleMatches = request.documents.filter((document) => document.kind === 'candidate_resume' && document.size_bytes === file.size);
        let saved = false;
        if (possibleMatches.length) {
          const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
          const fingerprint = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
          saved = possibleMatches.some((document) => document.sha256 === fingerprint);
        }
        const revision = saved ? request.revision : (
          await hiringRequest<Document & { request_revision: number }>(token, path + '/documents', uploadBody(file, 'candidate_resume'))
        ).request_revision;
        request = await hiringRequest<CandidateRequest>(token, path + '/submit', { expected_revision: revision });
      }

      if (!request.number || request.status !== 'submitted' || request.vacancy_ref?.id !== vacancy.id || request.vacancy_ref?.system !== vacancy.system || request.vacancy_ref?.revision !== vacancy.revision) {
        throw new Error('Обращение изменилось. Проверьте его состояние в личном кабинете.');
      }
      setSubmitted(request);
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : 'Не удалось отправить обращение.');
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <nav aria-label="Путь к вакансии" className="text-[13px] text-[#616977] flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={onGoHome} className="hover:text-[#1F4FD1] transition-colors">Вакансии</button>
        {vacancy && <><span aria-hidden="true">›</span><span className="text-[#141A24] font-medium">{vacancy.title}</span></>}
      </nav>
      {loadError ? (
        <div role="alert" className="bg-white border border-[#E1E5EB] rounded-2xl p-6">
          <p>{loadError}</p>
          <button type="button" onClick={() => setReload((current) => current + 1)} className="mt-3 text-[#1F4FD1] font-semibold">Повторить</button>
        </div>
      ) : !vacancy ? (
        <p role="status">{vacancyId ? 'Загружаем вакансию…' : 'Выберите вакансию в каталоге.'}</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <article className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-8 shadow-sm min-w-0">
            {vacancy.is_synthetic && <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">Учебная вакансия</span>
            </div>}
            <h1 className="text-[28px] sm:text-[34px] font-bold text-[#141A24] tracking-tight mb-2 break-words">{vacancy.title}</h1>
            {(vacancy.employer || vacancy.published_at) && <div className="text-[16px] text-[#616977] mb-8">
              {vacancy.employer && <p className="text-[18px] sm:text-[20px] font-bold text-[#141A24]">{vacancy.employer}</p>}
              {vacancy.published_at && <p className="mt-1 text-[13px]">Опубликовано {new Date(vacancy.published_at).toLocaleDateString('ru-RU')}</p>}
            </div>}
            <VacancyFacts vacancy={vacancy} />
          </article>

          <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-7 shadow-sm lg:sticky lg:top-24">
            {submitted ? (
              <div className="py-2" role="status">
                <div className="w-12 h-12 rounded-full bg-[#E6F4EA] flex items-center justify-center mb-4">
                  <img src="/icons/check.svg" alt="" className="w-6 h-6" />
                </div>
                <h2 className="text-[20px] font-bold text-[#141A24] mb-2">Обращение отправлено</h2>
                <p className="text-[14px] text-[#4A5363] mb-6">Номер {submitted.number}. Статус и документы доступны в личном кабинете.</p>
                <button type="button" className={primary} onClick={() => onGoCabinet?.(submitted.id)}>Перейти в личный кабинет</button>
              </div>
            ) : !token ? (
              <>
                <h2 className="text-[20px] font-bold text-[#141A24] mb-3">Откликнуться</h2>
                <p className="text-[13px] text-[#616977] mb-5">Войдите, чтобы отправить резюме по этой вакансии.</p>
                <button type="button" className={primary} onClick={onLogin}>Войти</button>
              </>
            ) : (
              <form onSubmit={submit}>
                <h2 className="text-[20px] font-bold text-[#141A24] mb-4">Откликнуться</h2>
                {draftId && error && <p className="text-[13px] text-[#616977]">Текст и контакт сохранены в черновике. Их можно изменить в личном кабинете.</p>}
                <label className="block mb-4 space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  О себе и желаемой работе
                  <textarea required className={field + ' py-2.5'} rows={3} value={message} disabled={busy || !!draftId} onChange={(event) => setMessage(event.target.value)} />
                </label>
                <label className="block mb-4 space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  Электронная почта
                  <input type="email" required className={field + ' h-11'} placeholder="name@mail.ru" value={email} disabled={busy || !!draftId} onChange={(event) => setEmail(event.target.value)} />
                </label>
                <label className="block mb-4 space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  Резюме
                  <input type="file" aria-label="Выбрать файл резюме" aria-required="true" accept="application/pdf,image/jpeg,image/png" className="sr-only peer" disabled={busy} onChange={(event) => {
                    setFile(event.target.files?.[0] ?? null);
                    event.target.value = '';
                  }} />
                  <span className="block bg-[#F5F8FF] border-2 border-dashed border-[#94B4FB] rounded-xl p-5 text-center cursor-pointer hover:bg-[#EEF3FE] transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-[#1F4FD1] peer-disabled:cursor-default" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
                    event.preventDefault();
                    if (!busy && event.dataTransfer.files[0]) setFile(event.dataTransfer.files[0]);
                  }}>
                    <span className="block text-[14px] font-bold text-[#141A24] mb-1 break-words">{file?.name || 'Перетащите резюме сюда'}</span>
                    <span className="block text-[12px] text-[#616977]">{file ? 'Нажмите, чтобы выбрать другой файл' : 'или выберите файл: PDF, JPEG или PNG'}</span>
                  </span>
                </label>
                {error && <p role="alert" className="text-[14px] text-[#A3171B]">{error}</p>}
                <PersonalDataLawLinks />
                <button type="submit" disabled={busy} className={primary}>{busy ? 'Отправляем…' : 'Отправить отклик'}</button>
                {draftId && error && <button type="button" onClick={() => onGoCabinet?.(draftId)} className="text-[14px] text-[#1F4FD1]">Открыть сохранённый черновик</button>}
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default VacancyPage;
