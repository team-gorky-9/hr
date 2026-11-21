import { serviceRequest, allPages } from "../components/employee/service";
export interface RecognitionEvent {
  id: string;
  revision: number;
  title: string;
  description: string;
  type: string;
  starts_at: string;
  ends_at: string;
  location: string;
  capacity: number;
  available_places: number;
  status: string;
  organizer_id: string;
  change_reason?: string;
  finish_reason?: string;
}
export interface Registration {
  id: string;
  event_id: string;
  actor_id: string;
  revision: number;
  participants_count: number;
  child_age_bands: string[];
  status: string;
  agreed_event_revision: number;
}
export interface Thanks {
  id: string;
  revision: number;
  text: string;
  status: string;
  author_id: string;
  recipient_id: string;
  recipient_choice?: string;
  moderation_status?: string;
  moderation_reason?: string;
}
export interface Material {
  id: string;
  title: string;
  description: string;
  url?: string;
  status: string;
  version: number;
  revision: number;
  author_actor_id: string;
}
export interface Campaign {
  id: string;
  title: string;
  criteria: string;
  starts_on: string;
  ends_on: string;
  status: string;
  revision: number;
  organizer_id: string;
  reviewer_actor_id: string;
}
export interface Nomination {
  id: string;
  campaign_id: string;
  author_id: string;
  nominee_id: string;
  statement: string;
  status: string;
  revision: number;
  decision_reason?: string;
  publication_choice: string;
}
export const recognitionRequest = <T>(
  token: string,
  path: string,
  body?: unknown,
  method?: string,
) => serviceRequest<T>("recognition", token, path, body, method);
export const recognitionList = <T>(token: string, path: string) =>
  allPages<T>("recognition", token, path);
