import React, { useEffect, useState } from 'react';
import { demoRolesEnabled, logoutSession, selectDemoRole, useSession } from './api/session';
import Header from './components/Header';
import HeroSection from './components/portal/HeroSection';
import CategoryCards from './components/portal/CategoryCards';
import NewVacanciesSection from './components/portal/NewVacanciesSection';
import WhyUsSection from './components/portal/WhyUsSection';
import ReserveCtaBanner from './components/portal/ReserveCtaBanner';
import VacancyPage from './pages/VacancyPage';
import StudentsWorkspace from './components/students/StudentsWorkspace';
import SupportPage from './components/support/SupportPage';
import DevelopmentPage from './components/development/DevelopmentPage';
import WorkforcePage from './components/workforce/WorkforcePage';
import HiringWorkspace from './components/hiring/HiringWorkspace';
import RequirementsPage from './components/requirements/RequirementsPage';
import ServiceAccess from './components/shared/ServiceAccess';

import HeaderHR, { HRNavTab } from './components/hr/HeaderHR';
import CandidatesDatabase, { CandidateRecord } from './components/hr/CandidatesDatabase';
import CandidateProfile from './components/hr/CandidateProfile';
import VacancyResponses from './components/hr/VacancyResponses';
import CandidateCard from './components/hr/CandidateCard';
import TelephoneInterview from './components/hr/TelephoneInterview';
import ArchivePage from './components/hr/ArchivePage';
import AnalyticsDashboard from './components/hr/AnalyticsDashboard';

import RoleHeader from './components/shared/RoleHeader';
import MyCandidates from './components/dept/MyCandidates';
import ReportPage from './components/report/ReportPage';
import Workspace from './components/employee/Workspace';
import Care from './components/employee/Care';
import Surveys from './components/employee/Surveys';

export type AppMode = 'portal' | 'hr' | 'dept' | 'employee';

const initialWorkspace = new URLSearchParams(window.location.search).get('workspace');
const employeeWorkspaces = ['support', 'development', 'workforce', 'onboarding', 'surveys'];
const initialEmployeeWorkspace = employeeWorkspaces.includes(initialWorkspace || '') ? initialWorkspace! : null;

const MODES: { id: AppMode; label: string }[] = [
  { id: 'portal', label: 'Портал соискателя' },
  { id: 'hr', label: 'Кабинет HR-менеджера' },
  { id: 'dept', label: 'ОПК' },
  { id: 'employee', label: 'Сотрудник' },
];

export type PortalRoute = 'home' | 'vacancies' | 'students' | 'practice' | 'cabinet' | 'login';

export const App: React.FC = () => {
  const { session } = useSession();
  const [sessionError, setSessionError] = useState('');
  const [roleRetry, setRoleRetry] = useState(0);
  const [portalVacancyId, setPortalVacancyId] = useState<string | null>(null);
  const [portalQuery, setPortalQuery] = useState('');
  const [requestId, setRequestId] = useState<string | undefined>();
  const [loginReturn, setLoginReturn] = useState<PortalRoute>('cabinet');
  const [databaseCandidate, setDatabaseCandidate] = useState<CandidateRecord | null>(null);
  const [databaseVacancyId, setDatabaseVacancyId] = useState('');
  const [interviewReturn, setInterviewReturn] = useState<'database' | 'vacancies'>('vacancies');
  // Mode: 'portal' (Соискатель) vs 'hr' (HR-менеджер)
  const [appMode, setAppMode] = useState<AppMode>(initialEmployeeWorkspace ? 'employee' : 'portal');
  const [employeeTab, setEmployeeTab] = useState<string>(initialEmployeeWorkspace || 'workspace');
  const [hrAnalyticsView, setHrAnalyticsView] = useState<'dashboard' | 'report'>('dashboard');
  const [opkTab, setOpkTab] = useState('mine');

  // Portal Routing State (Главная по умолчанию)
  const [portalRoute, setPortalRoute] = useState<PortalRoute>(initialWorkspace === 'practice' ? 'practice' : 'home');

  // HR Manager Routing State
  const [hrTab, setHrTab] = useState<HRNavTab>('database');
  const [dbView, setDbView] = useState<'list' | 'profile'>('list');
  const [hrView, setHrView] = useState<'list' | 'card'>('list');
  const [selectedResponseVacancyId, setSelectedResponseVacancyId] = useState<string>('');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>('');
  const demoLogin = ({ portal: 'candidate', hr: 'hr', dept: 'department', employee: 'employee' } as const)[appMode];
  const roleReady = !demoRolesEnabled || session?.actor.login === demoLogin;
  useEffect(() => {
    if (!demoRolesEnabled) return;
    let active = true;
    setSessionError('');
    void selectDemoRole(demoLogin).catch(error => { if (active) setSessionError(error instanceof Error ? error.message : 'Не удалось открыть роль'); });
    return () => { active = false; };
  }, [demoLogin, roleRetry]);


  useEffect(() => {
    if (session?.actor.grants.some(grant => grant.role === 'candidate') && portalRoute === 'login') setPortalRoute(loginReturn);
  }, [session, portalRoute, loginReturn]);
  const openVacancy = (id: string) => { setPortalVacancyId(id); setPortalRoute('vacancies'); window.scrollTo(0, 0); };
  const openCandidate = (candidate: CandidateRecord) => {
    setDatabaseCandidate(candidate);
    setSelectedCandidateId(candidate.applicationId || '');
    setDbView('profile');
    window.scrollTo(0, 0);
  };

  const handlePortalHome = () => {
    setPortalRoute('home');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePortalNav = (navId: string) => {
    if (navId === 'vacancies') {
      setPortalVacancyId(null);
      setPortalQuery('');
      setPortalRoute('vacancies');
    } else if (navId === 'practice') {
      setPortalRoute('practice');
    } else if (navId === 'students') {
      setPortalRoute('students');
    } else if (navId === 'cabinet') {
      setPortalRoute('cabinet');
    } else if (navId === 'home') {
      setPortalRoute('home');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-[#F3F5F8] text-[#141A24] flex flex-col font-sans">
      {/* ПЕРЕКЛЮЧАТЕЛЬ РЕЖИМОВ (ПОРТАЛ СОИСКАТЕЛЯ / КАБИНЕТ HR) */}
      <div className="bg-[#141A24] text-white text-[12px] px-4 sm:px-6 py-2 flex flex-wrap gap-2 items-center justify-between z-50">
        <div className="flex flex-wrap min-w-0 items-center gap-3">
          <span className="text-[#8E939D]">{demoRolesEnabled ? 'Учебные роли:' : 'Режим:'}</span>
          <div className="inline-flex flex-wrap rounded-lg bg-[#232832] p-0.5">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setAppMode(m.id);
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  appMode === m.id
                    ? 'bg-[#1F4FD1] text-white shadow-sm'
                    : 'text-[#BBBFC5] hover:text-white'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        <div className="text-[#8E939D] text-xs hidden sm:block">
          Кадровый ассистент
        </div>
        {session && !demoRolesEnabled && appMode !== 'portal' && <button type="button" className="text-xs text-white" onClick={async () => { try { await logoutSession(); setSessionError(''); } catch (error) { setSessionError(error instanceof Error ? error.message : 'Не удалось выйти'); } }}>Выйти</button>}
      </div>
      {sessionError && <p role="alert" className="px-6 py-2 text-red-700">{sessionError}</p>}

      {!roleReady && <div className="p-6">{sessionError || 'Открываем выбранную роль…'}{sessionError && <button className="ml-3 underline" onClick={() => setRoleRetry(n => n + 1)}>Повторить</button>}</div>}
      {/* ======================================================== */}
      {/* 1. ПОРТАЛ СОИСКАТЕЛЯ                                     */}
      {/* ======================================================== */}
      {roleReady && appMode === 'portal' && (
        <>
          <Header
            demoMode={demoRolesEnabled}
            authenticated={Boolean(session)}
            onLogoutClick={() => { void logoutSession().catch(error => setSessionError(String(error))); }}
            activeNav={portalRoute === 'home' ? '' : portalRoute}
            onLogoClick={handlePortalHome}
            onNavClick={handlePortalNav}
            onLoginClick={() => {
              setPortalRoute('cabinet');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />

          <main className="flex-1 max-w-[1216px] mx-auto px-4 sm:px-6 py-6 w-full space-y-8">
            {/* ГЛАВНАЯ СТРАНИЦА ПОРТАЛА (макет 1. Главная портала.png) */}
            {portalRoute === 'home' && (
              <>
                <HeroSection onSearch={(query: string) => { setPortalQuery(query); setPortalVacancyId(null); setPortalRoute('vacancies'); }} />

                <CategoryCards
                  onSelectCategory={(id) => {
                    if (id === 'vacancies') { setPortalVacancyId(null); setPortalRoute('vacancies'); }
                    else if (id === 'students') setPortalRoute('students');
                    else setPortalRoute('home');
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                />

                <NewVacanciesSection
                  onSelectVacancy={openVacancy}
                />

                <WhyUsSection />
                <ReserveCtaBanner />

              </>
            )}

            {/* ВАКАНСИЯ: ФОРМА ОТКЛИКА И ОТКЛИК ОТПРАВЛЕН (макеты 2 и 3) */}
            {portalRoute === 'vacancies' && !portalVacancyId && <NewVacanciesSection catalog query={portalQuery} onSelectVacancy={openVacancy} />}
            {portalRoute === 'vacancies' && portalVacancyId && (
              <VacancyPage
                vacancyId={portalVacancyId}
                token={session?.actor.grants.some(grant => grant.role === 'candidate') ? session.access_token : undefined}
                onLogin={() => { setLoginReturn('vacancies'); setPortalRoute('login'); }}
                onGoHome={() => { setPortalVacancyId(null); setPortalRoute('vacancies'); }}
                onGoCabinet={(id?: string) => {
                  setRequestId(id);
                  setPortalRoute('cabinet');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* СТУДЕНТАМ: ПРАКТИКА И МЕРОПРИЯТИЯ (макет 6) */}
            {(portalRoute === 'students' || portalRoute === 'practice') && <ServiceAccess initialLogin="candidate" allowedRoles={['candidate']}>
              {(token) => <StudentsWorkspace token={token} role="candidate" />}
            </ServiceAccess>}
            {portalRoute === 'login' && <ServiceAccess initialLogin="candidate" allowedRoles={['candidate']}>{() => <p>Вход выполнен…</p>}</ServiceAccess>}

            {/* ЛИЧНЫЙ КАБИНЕТ КАНДИДАТА (макет 5) */}
            {portalRoute === 'cabinet' && (
              <ServiceAccess initialLogin="candidate" allowedRoles={['candidate']}>{(token) => <HiringWorkspace audience="candidate" token={token} initialRequestId={requestId} />}</ServiceAccess>
            )}
          </main>
        </>
      )}

      {/* ======================================================== */}
      {/* 2. КАБИНЕТ HR-МЕНЕДЖЕРА                                 */}
      {/* ======================================================== */}
      {roleReady && appMode === 'hr' && (
        <>
          <HeaderHR
            managerName={session?.actor.grants.some(grant => ['hr', 'admin'].includes(grant.role)) ? `HR-менеджер · ${session.actor.login}` : 'HR-менеджер'}
            activeTab={hrTab}
            onTabChange={(tab) => {
              setHrTab(tab);
              setDbView('list');
              setHrView('list');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            onLogoClick={() => {
              setHrTab('database');
              setDbView('list');
              setHrView('list');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />

          <main className="flex-1 w-full">
            {/* 1. ЕДИНАЯ БАЗА: ТАБЛИЦА (макет 1) И ПРОФИЛЬ КАНДИДАТА (макеты 13–19) */}
            {hrTab === 'database' && dbView === 'list' && (
              <CandidatesDatabase
                vacancyId={databaseVacancyId}
                onVacancyChange={setDatabaseVacancyId}
                onSelectCandidate={openCandidate}
              />
            )}

            {/* МАКЕТЫ 13–19: ПРОФИЛЬ КАНДИДАТА И ДЕЙСТВИЯ */}
            {hrTab === 'database' && dbView === 'profile' && databaseCandidate && (
              <CandidateProfile
                candidate={databaseCandidate}
                selectedApplicationId={selectedCandidateId}
                onBackToDatabase={() => {
                  setDbView('list');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onOpenInterview={(applicationId: string) => {
                  setSelectedCandidateId(applicationId);
                  setInterviewReturn('database');
                  setHrTab('interview');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onOpenReserve={() => {
                  setHrTab('archive');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* 2 & 3. ОТКЛИКИ ПО ВАКАНСИЯМ + МАКЕТЫ 4 (Загрузка) и 5 (Ошибка) */}
            {hrTab === 'vacancies' && hrView === 'list' && (
              <VacancyResponses
                initialVacancyId={selectedResponseVacancyId}
                onOpenCard={(responseId: string, vacancyId: string) => {
                  setSelectedResponseVacancyId(vacancyId);
                  setSelectedCandidateId(responseId);
                  setHrView('card');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* КАРТОЧКА КАНДИДАТА: МАКЕТЫ 6–12 */}
            {hrTab === 'vacancies' && hrView === 'card' && (
              <CandidateCard
                candidateId={selectedCandidateId}
                onBack={() => {
                  setHrView('list');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onRequestClarification={() => { setInterviewReturn('vacancies'); setHrTab('interview'); }}
                onOpenArchive={() => setHrTab('archive')}
              />
            )}

            {/* 20. ТЕЛЕФОННОЕ ИНТЕРВЬЮ (макет 20. Телефонное интервью.png) */}
            {hrTab === 'interview' && (
              <TelephoneInterview
                applicationId={selectedCandidateId}
                onBackToCard={() => {
                  setHrTab(interviewReturn);
                  if (interviewReturn === 'database') setDbView('profile');
                  else setHrView('card');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* 24 & 25. КАДРОВЫЙ РЕЗЕРВ: КОНКУРС И СТУДЕНТЫ (макеты 24 и 25) */}
            {hrTab === 'archive' && <ArchivePage />}
            {hrTab === 'hiring' && <ServiceAccess allowedRoles={['hr', 'admin']}>{(token) => <HiringWorkspace token={token} />}</ServiceAccess>}
            {hrTab === 'requirements' && <ServiceAccess allowedRoles={['hr', 'admin', 'department']}>{(_token, role) => <RequirementsPage role={role === 'department' ? 'department' : 'hr'} />}</ServiceAccess>}

            {/* 21, 22, 23. АНАЛИТИКА И ОТЧЁТЫ (макеты 21, 22, 23) */}
            {hrTab === 'analytics' && (
              <>
                <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-6">
                  <div className="inline-flex bg-[#E8ECF2] rounded-xl p-1">
                    {([['dashboard', 'Аналитика подбора'], ['report', 'Годовой доклад']] as const).map(([id, l]) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setHrAnalyticsView(id)}
                        className={`px-4 py-2 rounded-lg text-[14px] font-semibold ${
                          hrAnalyticsView === id ? 'bg-white text-[#141A24] shadow-sm' : 'text-[#4A5363]'
                        }`}
                      >
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
                {hrAnalyticsView === 'dashboard' ? <AnalyticsDashboard /> : <ReportPage />}
              </>
            )}
          </main>
        </>
      )}
      {/* РУКОВОДИТЕЛЬ ДЕПАРТАМЕНТА: Мои кандидаты */}
      {roleReady && appMode === 'dept' && (
        <>
          <RoleHeader
            tabs={[{ id: 'mine', label: 'Мои кандидаты' }, { id: 'analytics', label: 'Аналитика' }]}
            activeTab={opkTab}
            onTabChange={setOpkTab}
            roleLabel="ОПК"
          />
          <main className="flex-1 w-full">
            {opkTab === 'mine' && <MyCandidates />}
            {opkTab === 'analytics' && <>
              <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-6">
                <div className="inline-flex bg-[#E8ECF2] rounded-xl p-1">
                  {([['dashboard', 'Аналитика подбора'], ['report', 'Годовой доклад']] as const).map(([id, label]) =>
                    <button key={id} type="button" onClick={() => setHrAnalyticsView(id)} className={`px-4 py-2 rounded-lg text-[14px] font-semibold ${hrAnalyticsView === id ? 'bg-white text-[#141A24] shadow-sm' : 'text-[#4A5363]'}`}>{label}</button>)}
                </div>
              </div>
              {hrAnalyticsView === 'dashboard' ? <AnalyticsDashboard /> : <ReportPage />}
            </>}
          </main>
        </>
      )}

      {/* СОТРУДНИК ДЕПАРТАМЕНТА */}
      {roleReady && appMode === 'employee' && (
        <>
          <RoleHeader
            tabs={[
              { id: 'workspace', label: 'Рабочее пространство' },
              { id: 'care', label: 'Забота и мотивация' },
              { id: 'support', label: 'Материальная помощь' },
              { id: 'surveys', label: 'Опросы' },
            ]}
            activeTab={employeeTab}
            onTabChange={setEmployeeTab}
            roleLabel={demoRolesEnabled ? "Специалист департамента экономики · Кирилл Л. (учебный)" : "Кабинет сотрудника"}
            onLogoClick={() => setEmployeeTab('workspace')}
          />
          <main className="flex-1 w-full">
            {employeeTab === 'workspace' && <ServiceAccess initialLogin="employee" allowedRoles={['employee']}>
              {() => <Workspace onNavigate={setEmployeeTab} />}
            </ServiceAccess>}
            {employeeTab === 'care' && <Care onNavigate={setEmployeeTab} />}
            {employeeTab === 'support' && <SupportPage />}
            {employeeTab === 'development' && <ServiceAccess initialLogin="employee" allowedRoles={['employee', 'department', 'hr', 'admin']}>{() => <DevelopmentPage />}</ServiceAccess>}
            {employeeTab === 'workforce' && <ServiceAccess initialLogin="hr" allowedRoles={['hr', 'admin']}>{() => <WorkforcePage />}</ServiceAccess>}
            {employeeTab === 'onboarding' && <ServiceAccess initialLogin="employee" allowedRoles={['employee', 'hr', 'admin']}>{() => <WorkforcePage initialTab="onboarding" />}</ServiceAccess>}
            {employeeTab === 'surveys' && <Surveys />}
          </main>
        </>
      )}
    </div>
  );
};

export default App;
