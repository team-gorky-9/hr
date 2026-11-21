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

const field = 'w-full px-3.5 py-2.5 bg-white border border-[#E1E5EB] rounded-lg text-[14px] text-[#141A24]';
const primary = 'w-full min-h-11 px-4 bg-[#1F4FD1] hover:bg-[#1841B2] text-white font-medium text-[14px] rounded-lg transition-colors disabled:opacity-60';

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
            {vacancy.is_synthetic && <span className="inline-block mb-3 px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">Учебная вакансия</span>}
            <h1 className="text-[26px] sm:text-[32px] font-bold text-[#141A24] leading-tight break-words">{vacancy.title}</h1>
            {vacancy.employer && <p className="mt-3 text-[14px] text-[#4A5363]">{vacancy.employer}</p>}
            {vacancy.published_at && <p className="mt-3 text-[13px] text-[#616977]">
              Опубликовано {new Date(vacancy.published_at).toLocaleDateString('ru-RU')}
            </p>}
            <h2 className="mt-7 mb-3 font-bold text-[18px] text-[#141A24]">О вакансии</h2>
            <p className="whitespace-pre-wrap break-words leading-relaxed text-[#4A5363]">{vacancy.description || 'Подробное описание вакансии пока отсутствует.'}</p>
          </article>

          <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-7 shadow-sm lg:sticky lg:top-24">
            {submitted ? (
              <div className="py-2" role="status">
                <div className="mb-3 rounded-full bg-[#E6F4EA] w-12 h-12 flex items-center justify-center">
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
              <form onSubmit={submit} className="space-y-4">
                <h2 className="text-[20px] font-bold text-[#141A24]">Откликнуться</h2>
                {draftId && error && <p className="text-[13px] text-[#616977]">Текст и контакт сохранены в черновике. Их можно изменить в личном кабинете.</p>}
                <label className="block space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  О себе и желаемой работе
                  <textarea required className={field} rows={3} value={message} disabled={busy || !!draftId} onChange={(event) => setMessage(event.target.value)} />
                </label>
                <label className="block space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  Электронная почта
                  <input type="email" required className={field} value={email} disabled={busy || !!draftId} onChange={(event) => setEmail(event.target.value)} />
                </label>
                <label className="block space-y-1.5 text-[13px] font-medium text-[#141A24]">
                  Резюме
                  <span className="block bg-[#F5F8FF] border-2 border-dashed border-[#94B4FB] rounded-xl p-3">
                    <span className="block mb-2 text-[#616977]">Выберите PDF, JPEG или PNG</span>
                    <input type="file" required accept="application/pdf,image/jpeg,image/png" className="block max-w-full text-[13px] file:mr-2 file:border-0 file:rounded-md file:px-2 file:py-1 file:bg-white" disabled={busy} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
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
