import { Btn, Card, PageTitle } from '../shared/ui';

export default function Care({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div className="rounded-3xl bg-[#F1EDFF] p-8">
      <PageTitle title="Забота и мотивация" />
    </div>
    <Card className="space-y-3">
      <p>Запись на мероприятия пока недоступна.</p>
      {onNavigate && <Btn onClick={() => onNavigate('support')}>Открыть материальную помощь</Btn>}
    </Card>
  </div>;
}

