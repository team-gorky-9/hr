import { useEffect, useState, type FormEvent } from "react";
import { publicVacancy, type PublicVacancy } from "../api/portal";
import {
  hiringRequest,
  uploadBody,
  hiringStatus,
  type CandidateRequest,
} from "../api/hiring";
import ServiceAccess from "../components/shared/ServiceAccess";

interface VacancyPageProps {
  vacancyId?: string;
  onGoHome?: () => void;
  onGoVacancies?: () => void;
  onGoCabinet?: () => void;
  initialSubmitted?: boolean;
}

function ApplicationForm({
  vacancy,
  token,
  login,
  onGoCabinet,
}: {
  vacancy: PublicVacancy;
  token: string;
  login: string;
  onGoCabinet?: () => void;
}) {
  const storageKey = `portal-request:${login}:${vacancy.id}`;
  const [fio, setFio] = useState(""),
    [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null),
    [agreed, setAgreed] = useState(false);
  const [request, setRequest] = useState<CandidateRequest | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const id = sessionStorage.getItem(storageKey);
    if (id) {
      setBusy(true);
      hiringRequest<CandidateRequest>(token, "/candidate-requests/" + id)
        .then((row) => {
          if (active) {
            setRequest(row);
            setEmail(row.contact.value);
            setFio(row.message.split("\n")[0].replace(/^ФИО: /, ""));
          }
        })
        .catch((e) => {
          if (active)
            setError(
              e instanceof Error
                ? e.message
                : "Не удалось восстановить обращение",
            );
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }
    return () => {
      active = false;
    };
  }, [token, storageKey]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !agreed) return;
    if (
      file &&
      (file.size > 20 * 1024 * 1024 || !/\.(pdf|doc|docx)$/i.test(file.name))
    ) {
      setError("Выберите PDF, DOC или DOCX размером до 20 МБ.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let row = request;
      const savedId = sessionStorage.getItem(storageKey);
      if (savedId)
        row = await hiringRequest<CandidateRequest>(
          token,
          "/candidate-requests/" + savedId,
        );
      if (row && row.status !== "draft") {
        setRequest(row);
        return;
      }
      const message = `ФИО: ${fio.trim()}\nОтклик на вакансию «${vacancy.title}».\nСогласие на обработку персональных данных подтверждено при подаче.`;
      if (!row) {
        // Retain the create key across a lost response/retry, so one form cannot create duplicates.
        const keyName = storageKey + ":create-key";
        let key = sessionStorage.getItem(keyName);
        if (!key) {
          key = crypto.randomUUID();
          sessionStorage.setItem(keyName, key);
        }
        const env = (
          import.meta as ImportMeta & { env: Record<string, string> }
        ).env;
        const base = (env.VITE_HIRING_API_BASE || "/hiring-api").replace(
          /\/$/,
          "",
        );
        // Freeze the first body together with its idempotency key; edits are patched below.
        const bodyName = storageKey + ":create-body";
        let body = sessionStorage.getItem(bodyName);
        if (!body) {
          body = JSON.stringify({
            message,
            contact: { channel: "email", value: email.trim() },
            vacancy_ref: {
              system: "requirements",
              id: vacancy.id,
              revision: vacancy.revision,
            },
          });
          sessionStorage.setItem(bodyName, body);
        }
        const response = await fetch(base + "/candidate-requests", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
            "Idempotency-Key": key,
          },
          body,
        });
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            data?.error?.message ||
              `Не удалось создать обращение (${response.status}).`,
          );
        row = data as CandidateRequest;
        sessionStorage.setItem(storageKey, row.id);
        sessionStorage.removeItem(bodyName);
        setRequest(row);
      }
      if (row.message !== message || row.contact.value !== email.trim())
        row = await hiringRequest<CandidateRequest>(
          token,
          "/candidate-requests/" + row.id,
          {
            expected_revision: row.revision,
            message,
            contact: { channel: "email", value: email.trim() },
          },
          "PATCH",
        );
      const fileHash = file
        ? Array.from(
            new Uint8Array(
              await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
            ),
          )
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("")
        : null;
      if (
        file &&
        !row.documents.some(
          (d) => (d as typeof d & { sha256?: string }).sha256 === fileHash,
        )
      ) {
        await hiringRequest(
          token,
          `/candidate-requests/${row.id}/documents`,
          uploadBody(file, "candidate_resume"),
        );
        row = await hiringRequest<CandidateRequest>(
          token,
          "/candidate-requests/" + row.id,
        );
      }
      if (!row.documents.length)
        throw new Error(
          "Приложите резюме, чтобы отправить отклик. Черновик сохранён.",
        );
      const submitted = await hiringRequest<CandidateRequest>(
        token,
        `/candidate-requests/${row.id}/submit`,
        { expected_revision: row.revision },
      );
      setRequest(submitted);
      setFile(null);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Не удалось отправить отклик. Повторите попытку.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (request && request.status !== "draft")
    return (
      <div className="py-2">
        <div className="w-12 h-12 rounded-full bg-[#E6F4EA] flex items-center justify-center mb-4">
          <img src="/icons/check.svg" alt="" className="w-6 h-6" />
        </div>
        <h2 className="text-[20px] font-bold text-[#141A24] mb-2">
          Обращение {request.number}:{" "}
          {hiringStatus[request.status] || request.status}
        </h2>
        <p className="text-[14px] text-[#4A5363] leading-relaxed mb-6">
          Резюме и выбранная вакансия сохранены. Статус, вопросы кадровика и
          результат доступны в личном кабинете.
        </p>
        {request.target_question && (
          <p className="text-amber-800 mb-4">
            {request.target_question === "vacancy_closed"
              ? "Вакансия закрылась до подачи. Кадровик уточнит цель обращения."
              : "Цель обращения требует уточнения кадровиком."}
          </p>
        )}
        <button
          onClick={() => {
            const url = new URL(location.href);
            url.searchParams.set("candidate_request", request.id);
            history.replaceState(null, "", url);
            onGoCabinet?.();
          }}
          className="w-full h-11 bg-[#1F4FD1] text-white rounded-lg"
        >
          Перейти в личный кабинет
        </button>
        {["closed", "withdrawn"].includes(request.status) && (
          <button
            type="button"
            className="w-full mt-3 h-11 border border-[#E1E5EB] text-[#1F4FD1] rounded-lg"
            onClick={() => {
              sessionStorage.removeItem(storageKey);
              sessionStorage.removeItem(storageKey + ":create-key");
              sessionStorage.removeItem(storageKey + ":create-body");
              setRequest(null);
              setFile(null);
              setAgreed(false);
              setError("");
            }}
          >
            Создать новое обращение
          </button>
        )}
      </div>
    );
  return (
    <form onSubmit={submit}>
      <h2 className="text-[20px] font-bold text-[#141A24] mb-1">
        Откликнуться
      </h2>
      <p className="text-[13px] text-[#616977] mb-5">
        Обращение будет доступно в вашем личном кабинете.
      </p>
      <fieldset disabled={busy} className="space-y-4">
        <label className="block text-[13px] font-medium">
          ФИО
          <input
            required
            value={fio}
            onChange={(e) => setFio(e.target.value)}
            className="block w-full h-11 px-3.5 mt-1.5 border border-[#E1E5EB] rounded-lg text-[14px]"
          />
        </label>
        <label className="block text-[13px] font-medium">
          Электронная почта
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="block w-full h-11 px-3.5 mt-1.5 border border-[#E1E5EB] rounded-lg text-[14px]"
          />
        </label>
        <label className="block bg-[#F5F8FF] border-2 border-dashed border-[#94B4FB] rounded-xl p-5 text-center cursor-pointer">
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <strong className="text-[14px]">
            {file?.name ||
              request?.documents[0]?.original_name ||
              "Выберите резюме"}
          </strong>
          <span className="block text-[12px] text-[#616977] mt-1">
            PDF, DOC или DOCX до 20 МБ
          </span>
        </label>
        <label className="flex items-start gap-2.5 text-[13px]">
          <input
            type="checkbox"
            required
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            className="mt-1"
          />
          Согласен на обработку персональных данных (152-ФЗ)
        </label>
        <button
          type="submit"
          className="w-full h-11 bg-[#1F4FD1] hover:bg-[#1841B2] text-white font-medium text-[14px] rounded-lg disabled:opacity-50"
        >
          {busy ? "Сохраняем…" : "Отправить отклик"}
        </button>
      </fieldset>
      {error && (
        <p role="alert" className="text-[13px] text-[#B06000] mt-3">
          {error}
        </p>
      )}
      {request?.status === "draft" && (
        <p className="text-[12px] text-[#616977] mt-3">
          Черновик сохранён. При ошибке можно повторить отправку.
        </p>
      )}
    </form>
  );
}

export default function VacancyPage({
  vacancyId,
  onGoHome,
  onGoVacancies,
  onGoCabinet,
}: VacancyPageProps) {
  const [vacancy, setVacancy] = useState<PublicVacancy | null>(null),
    [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setVacancy(null);
    setError("");
    if (!vacancyId) {
      setError("Выберите вакансию из каталога.");
      return;
    }
    publicVacancy(vacancyId, controller.signal)
      .then(setVacancy)
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Ошибка загрузки");
      });
    return () => controller.abort();
  }, [vacancyId, refresh]);
  return (
    <div className="space-y-6">
      <nav className="text-[13px] text-[#616977] flex items-center gap-1.5">
        <button onClick={onGoHome}>Главная</button>
        <span>›</span>
        <button onClick={onGoVacancies || onGoHome}>Вакансии</button>
        {vacancy && (
          <>
            <span>›</span>
            <span className="text-[#141A24] font-medium">{vacancy.title}</span>
          </>
        )}
      </nav>
      {error ? (
        <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6">
          <p role="alert">{error}</p>
          <button
            className="text-[#1F4FD1] mt-3"
            onClick={() => setRefresh((x) => x + 1)}
          >
            Повторить
          </button>
        </div>
      ) : !vacancy ? (
        <p role="status">Загружаем вакансию…</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-8 shadow-sm">
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">
              {vacancy.status === "published"
                ? vacancy.department_name || "Открытая вакансия"
                : "Вакансия закрыта"}
            </span>
            <h1 className="text-[28px] sm:text-[34px] font-bold text-[#141A24] tracking-tight mt-3 mb-2">
              {vacancy.title}
            </h1>
            <p className="text-[13px] text-[#616977] mb-8">
              Опубликовано{" "}
              {new Date(vacancy.published_at).toLocaleDateString("ru-RU")}
            </p>
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">
              О вакансии
            </h2>
            <p className="whitespace-pre-wrap text-[14px] text-[#334155] leading-relaxed">
              {vacancy.description}
            </p>
          </div>
          <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-7 shadow-sm sticky top-24">
            {vacancy.status === "closed" ? (
              <>
                <h2 className="text-[20px] font-bold mb-3">
                  Приём откликов завершён
                </h2>
                <button className="text-[#1F4FD1]" onClick={onGoVacancies}>
                  Посмотреть другие вакансии
                </button>
              </>
            ) : (
              <ServiceAccess
                initialLogin="candidate"
                requiredRoles={["candidate"]}
              >
                {(token, login) => (
                  <ApplicationForm
                    key={`${login}:${vacancy.id}`}
                    vacancy={vacancy}
                    token={token}
                    login={login}
                    onGoCabinet={onGoCabinet}
                  />
                )}
              </ServiceAccess>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
