import { useState } from 'react';
import { Btn } from '../shared/ui';
export type Field = { name: string; label: string; type?: string; optional?: boolean; value?: string; options?: [string, string][] };
export const fieldClass = 'w-full border border-[#C9D0DB] rounded-lg px-3 py-2 text-[14px] bg-white focus:outline-[#1F4FD1]';
export function ActionForm({ title, fields = [], submit = 'Сохранить', onSubmit, busy, note }: {
  title: string; fields?: Field[]; submit?: string; busy: boolean; note?: string;
  onSubmit: (values: Record<string, string>, form: HTMLFormElement) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  return <details open={open} onToggle={e => setOpen(e.currentTarget.open)} className="border border-[#E1E5EB] rounded-xl p-4">
    <summary className="cursor-pointer font-semibold text-[#141A24]">{title}</summary>
    {open && <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); const form = e.currentTarget;
      const values = Object.fromEntries([...new FormData(form).entries()].filter(([, v]) => typeof v === 'string')) as Record<string, string>;
      void onSubmit(values, form).then(() => { form.reset(); setOpen(false); }).catch(() => {});
    }}>
      {note && <p className="text-sm text-[#616977]">{note}</p>}
      {fields.map(f => <label key={f.name} className="block text-sm text-[#4A5363]">{f.label}
        {f.options ? <select name={f.name} defaultValue={f.value} required={!f.optional} className={fieldClass}>{f.options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select>
          : f.type === 'textarea' ? <textarea name={f.name} required={!f.optional} defaultValue={f.value} maxLength={4000} className={fieldClass} rows={3} />
          : <input name={f.name} type={f.type || 'text'} required={!f.optional} defaultValue={f.type === 'file' ? undefined : f.value} className={fieldClass} />}
      </label>)}
      <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Сохраняем…' : submit}</Btn>
    </form>}
  </details>;
}
export const textField = (name: string, label: string, optional = false): Field => ({ name, label, optional });
export const longField = (name: string, label: string): Field => ({ name, label, type: 'textarea' });
export const reasonField = longField('reason', 'Причина');

