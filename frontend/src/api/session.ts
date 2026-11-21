import { developmentRequest, type Actor, type Session } from "./development";

const tokenKey = "workforce-access-token";
export const sessionChanged = "workforce-session-changed";
export function sessionToken(): string | null {
  return sessionStorage.getItem(tokenKey);
}
export function saveSession(session: Session): void {
  sessionStorage.setItem(tokenKey, session.access_token);
  window.dispatchEvent(new Event(sessionChanged));
}
export function forgetSession(token?: string): void {
  if (token && sessionToken() !== token) return;
  sessionStorage.removeItem(tokenKey);
  window.dispatchEvent(new Event(sessionChanged));
}
export async function restoreSession(): Promise<Session | null> {
  const token = sessionToken();
  if (!token) return null;
  const actor = await developmentRequest<Actor>(token, "/session");
  return sessionToken() === token ? { access_token: token, actor } : null;
}
export async function endSession(token: string): Promise<void> {
  await developmentRequest(token, "/session", undefined, "DELETE");
  forgetSession(token);
}
export function requireSessionToken(): string {
  const token = sessionToken();
  if (!token) throw new Error("Войдите в рабочий раздел, чтобы продолжить.");
  return token;
}
