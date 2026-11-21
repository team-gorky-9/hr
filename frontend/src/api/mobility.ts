import { serviceRequest } from "../components/employee/service";
export interface Opportunity {
  id: string;
  revision: number;
  title: string;
  result_description: string;
  starts_on: string;
  ends_on: string;
  time_percent: number;
  status: string;
  owner_actor_id: string;
}
export interface Interest {
  id: string;
  revision: number;
  opportunity_id: string;
  employee_actor_id: string;
  status: string;
  comment: string;
  reason: string | null;
}
export interface Proposal {
  id: string;
  revision: number;
  interest_id: string;
  employee_actor_id: string;
  owner_actor_id: string;
  manager_actor_id: string;
  starts_on: string;
  ends_on: string;
  time_percent: number;
  status: string;
  reason: string | null;
  employee_response: string | null;
  manager_response: string | null;
  conditions_revision: number;
}
export interface Participation {
  id: string;
  revision: number;
  opportunity_id: string;
  opportunity_title: string;
  employee_actor_id: string;
  owner_actor_id: string;
  status: string;
  starts_on: string;
  ends_on: string;
  time_percent: number;
  result_note: string | null;
  employee_feedback: { accepted: boolean; note: string } | null;
  result_packages?: {
    id: string;
    purpose: string;
    share_allowed: boolean;
    delivery_status: string;
  }[];
}
export interface VacancyInterest {
  id: string;
  revision: number;
  vacancy_ref: string;
  publication_revision: number;
  employee_actor_id: string;
  comment: string;
  status: string;
  consideration_ref: string | null;
  confirmation_basis: string | null;
}
export interface ManagerAssignment {
  employee_actor_id: string;
  manager_actor_id: string;
  source_reference: string;
}
export const mobilityRequest = <T>(
  token: string,
  path: string,
  body?: unknown,
  method?: string,
) => serviceRequest<T>("mobility", token, path, body, method);
