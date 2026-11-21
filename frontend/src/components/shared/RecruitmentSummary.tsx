import { assessmentLabel, humanizeInterview, readableExplanation, resultLabel, stageLabel, type HandoffSummary } from '../../api/recruitment';
import { Badge } from '../shared/ui';

const staleLabels: Record<string, string> = {
  text_changed: 'обновилось резюме', profile_changed: 'обновился профиль должности',
  algorithm_changed: 'обновился алгоритм оценки',
};
const gapLabels: Record<string, string> = {
  card_missing: 'Не хватает в резюме', screening_unknown: 'Не подтверждено на первичном отборе',
  interview_requirements: 'Проверить на собеседовании',
};
const basisLabels: Record<string, string> = {
  resume: 'по резюме', interview: 'по итогам собеседования', documents: 'по документам',
  document: 'по документу', test: 'по результату задания',
};
const interviewLabels: Record<string, string> = {
  continue: 'Продолжить рассмотрение', stop: 'Остановить рассмотрение',
  no_answer: 'Не удалось связаться', pending: 'Итог ещё не записан', completed: 'Собеседование завершено',
};

export default function RecruitmentSummary({ summary }: { summary: HandoffSummary }) {
  const assessment = summary.formal_summary;
  const brief = summary.candidate_brief;
  return <section className="space-y-4 rounded-xl bg-[#F6F7F9] p-4 text-sm break-words">
    <div className="space-y-1">
      <h3 className="text-base font-bold">Сводка по кандидату {summary.candidate_code}</h3>
      {summary.vacancy && <p>Вакансия · {summary.vacancy.title}</p>}
      {summary.posting_title && summary.posting_title !== summary.vacancy?.title && <p>Публикация · {summary.posting_title}</p>}
      <p>Этап · {stageLabel(summary.stage.title)}</p>
    </div>
    {summary.warnings.length > 0 && <ul className="list-disc pl-5 text-[#8A4B0A]">
      {summary.warnings.map((warning, index) => {
        const label = warning.startsWith('Актуальная оценка отсутствует (') ? assessmentLabel(summary.assessment_status)
          : warning.startsWith('Оценка устарела (') ? `Оценка устарела${summary.stale_reason && staleLabels[summary.stale_reason] ? ' · ' + staleLabels[summary.stale_reason] : ''}`
          : warning;
        return <li key={index}>{label}</li>;
      })}
    </ul>}
    {(brief.headline || brief.experience_years != null || !!brief.skills?.length) && <div className="space-y-1">
      <h4 className="font-bold">Профессиональный профиль</h4>
      {brief.headline && <p>{brief.headline}</p>}
      {brief.experience_years != null && <p>Заявленный стаж · {brief.experience_years} г.</p>}
      {!!brief.skills?.length && <p>Навыки · {brief.skills.map(skill => skill.name).join(', ')}</p>}
    </div>}
    <div className="space-y-2">
      <h4 className="font-bold">Оценка</h4>
      <Badge tone={summary.assessment_status === 'ready' ? 'green' : 'amber'}>{assessmentLabel(summary.assessment_status)}</Badge>
      {assessment && <>
        <p>Формальный итог · {resultLabel(assessment.formal_result)}{assessment.formal_preliminary && ' · предварительно'}</p>
        {assessment.overall_score != null && <p>Балл по компетенциям · {assessment.overall_score}</p>}
        {assessment.summary && <p>{assessment.summary}</p>}
        <ul className="list-disc pl-5 space-y-1">
          {assessment.formal_checks.map(check => <li key={check.requirement_id}>
            {check.description} <strong>· {resultLabel(check.result)}</strong>
            {basisLabels[check.basis] && ` · ${basisLabels[check.basis]}`}
            {check.is_preliminary && ' · предварительно'}
            {check.check_stage === 'interview' && ' · проверить на собеседовании'}
          </li>)}
        </ul>
      </>}
    </div>
    {summary.competencies.length > 0 && <div className="space-y-2">
      <h4 className="font-bold">Компетенции и основания</h4>
      {summary.competencies.map((item, index) => <div key={index}>
        <p className="font-medium">{item.name}{item.level != null && ` · уровень ${item.level}`}</p>
        {readableExplanation(item.explanation) && <p>{readableExplanation(item.explanation)}</p>}
        {item.evidence?.map((evidence, index) => <p key={index}>«{evidence.quote}»</p>)}
      </div>)}
    </div>}
    {Object.entries(gapLabels).map(([key, label]) => summary.gaps[key]?.length ? <div key={key}>
      <h4 className="font-bold">{label}</h4>
      <ul className="list-disc pl-5">{summary.gaps[key].map((item, index) => <li key={index}>{item}</li>)}</ul>
    </div> : null)}
    {!!summary.interview_notes.length && <div className="space-y-2">
      <h4 className="font-bold">Итоги собеседования</h4>
      {summary.interview_notes.map(item => <div key={item.interview_id}>
        <strong>{item.kind === 'phone' ? 'Телефонное собеседование' : 'Собеседование в подразделении'} · {interviewLabels[item.result] || 'Итог не указан'}</strong>
        {item.summary && <p>{humanizeInterview(item.summary)}</p>}
        {item.questions.map(question => <p key={question.question_id}>{question.question} · {question.answer_text || 'Ответ не записан'}</p>)}
      </div>)}
    </div>}
    {!!summary.hr_notes.length && <div className="space-y-2">
      <h4 className="font-bold">Заметки сотрудника по подбору персонала</h4>
      {summary.hr_notes.map(note => <p key={note.seq}><strong>{stageLabel(note.stage_title)}</strong> · {note.text}</p>)}
    </div>}
  </section>;
}
