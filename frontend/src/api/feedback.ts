import { serviceRequest, type Page } from "../components/employee/service";
export interface Cycle {
  id: string;
  title: string;
  status: string;
  revision: number;
  question_version: string;
  groups?: { key: string; label: string; eligible_count: number }[];
}
export interface SurveyForm {
  id: string;
  title: string;
  status: string;
  privacy_notice: string;
  questions: { key: string; text: string; min: number; max: number }[];
  topic_options: { key: string; label: string }[];
}
export interface ConfidentialCase {
  id: string;
  revision: number;
  subject: string;
  text: string;
  status: string;
  author_actor_id: string;
  recipient_actor_id: string;
  reply: string | null;
  close_reason: string | null;
  notice: string;
  response_terms: string;
}
export interface Outcome {
  messages: {
    id: string;
    text: string;
    measures: {
      id: string;
      text: string;
      status: string;
      outcome_note: string | null;
    }[];
  }[];
  notice: string;
}
export const feedbackRequest = <T>(
  token: string | null,
  path: string,
  body?: unknown,
  method?: string,
) => serviceRequest<T>("feedback", token, path, body, method);
export const feedbackApi = {
  cycles: (token: string) => feedbackRequest<Page<Cycle>>(token, "/cycles"),
  form: (id: string) => feedbackRequest<SurveyForm>(null, `/cycles/${id}/form`),
  outcome: (token: string, id: string) =>
    feedbackRequest<Outcome>(token, `/cycles/${id}/outcome`),
};
