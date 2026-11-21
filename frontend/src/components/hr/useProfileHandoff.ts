import { useEffect, useState } from 'react';
import { addWorkingDays, isDateOnly, moscowDay, RESPONSE_WORKING_DAYS } from './handoffDeadline';

export interface ProfileHandoff {
  sentOn: string;
  dueOn: string;
  department: string;
  recipient: string;
}

export function newProfileHandoff(sentOn: string): ProfileHandoff {
  return {
    sentOn, dueOn: addWorkingDays(sentOn, RESPONSE_WORKING_DAYS),
    department: 'Департамент цифрового развития', recipient: 'Андрей Г., директор департамента',
  };
}

function readHandoff(key: string): { handoff: ProfileHandoff | null; error: string } {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { handoff: null, error: '' };
    const value = JSON.parse(raw);
    if (!value || !isDateOnly(value.sentOn) || !isDateOnly(value.dueOn) || value.dueOn <= value.sentOn
      || typeof value.department !== 'string' || typeof value.recipient !== 'string') {
      throw new Error('Invalid saved handoff');
    }
    return { handoff: value, error: '' };
  } catch {
    return { handoff: null, error: 'Не удалось прочитать сохранённый срок. Проверьте данные перед направлением.' };
  }
}

// This screen has demo candidate IDs, not application UUIDs. Keep each timer
// separate and never claim that local persistence sends a server notification.
export function useProfileHandoff(candidateId: string) {
  const key = `hr:profile-handoff:v1:${candidateId}`;
  const [state, setState] = useState(() => readHandoff(key));
  const [today, setToday] = useState(moscowDay);

  useEffect(() => {
    const refresh = () => setToday(moscowDay());
    const timer = window.setInterval(refresh, 30_000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, []);

  const saveHandoff = (handoff: ProfileHandoff | null) => {
    try {
      if (handoff) localStorage.setItem(key, JSON.stringify(handoff));
      else localStorage.removeItem(key);
      setState({ handoff, error: '' });
    } catch {
      setState({ handoff, error: 'Срок изменён только в этой вкладке: браузер не разрешил сохранить его.' });
    }
  };
  return { ...state, saveHandoff, today };
}
