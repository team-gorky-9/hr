import { useEffect, useState } from "react";
import {
  api,
  errorMessage,
  uploadCandidate,
  type Vacancy,
} from "../../api/recruitment";
export function CandidateUpload({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [vacancies, setVacancies] = useState<Vacancy[]>([]),
    [vacancyId, setVacancyId] = useState("");
  const [file, setFile] = useState<File | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api
      .vacancies(controller.signal)
      .then((result) => {
        setVacancies(result.items);
        setVacancyId(result.items[0]?.vacancy_id || "");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, []);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Загрузка резюме"
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
    >
      <form
        className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl border border-[#E1E5EB]"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!file || !vacancyId) return;
          setBusy(true);
          setError("");
          try {
            const result = await uploadCandidate(file, vacancyId);
            onSaved(
              result.status === "duplicate_skipped"
                ? "Это резюме уже загружено. Существующее рассмотрение сохранено."
                : "Резюме сохранено, рассмотрение создано. Оценка ещё не выполнена.",
            );
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2 className="text-lg font-bold">Загрузить резюме</h2>
        <p className="text-sm text-[#616977]">
          Выберите вакансию. TXT, DOCX или PDF с текстовым слоем, до 10 МБ. Файл
          пройдёт извлечение и очистку персональных данных.
        </p>
        <label className="block text-sm">
          Вакансия
          <select
            required
            className="block w-full border rounded-lg p-2 mt-1"
            value={vacancyId}
            onChange={(e) => setVacancyId(e.target.value)}
          >
            {vacancies.map((v) => (
              <option key={v.vacancy_id} value={v.vacancy_id}>
                {v.title}
              </option>
            ))}
          </select>
        </label>
        <input
          aria-label="Файл резюме"
          required
          type="file"
          accept=".txt,.pdf,.docx"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        {error && (
          <p role="alert" className="text-red-700 text-sm">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button type="button" disabled={busy} onClick={onClose}>
            Отмена
          </button>
          <button
            type="submit"
            disabled={busy || !file || !vacancyId}
            className="px-4 py-2 rounded-lg bg-[#1F4FD1] text-white disabled:opacity-40"
          >
            {busy ? "Сохраняем…" : "Загрузить"}
          </button>
        </div>
      </form>
    </div>
  );
}
