import React, { useState } from 'react';
import Header from './components/Header';
import HeroSection from './components/portal/HeroSection';
import CategoryCards from './components/portal/CategoryCards';
import NewVacanciesSection from './components/portal/NewVacanciesSection';
import WhyUsSection from './components/portal/WhyUsSection';
import ReserveCtaBanner from './components/portal/ReserveCtaBanner';
import VacancyPage from './pages/VacancyPage';
import StudentsPage from './pages/StudentsPage';
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
import TalentReserve from './components/hr/TalentReserve';
import ArchivePage from './components/hr/ArchivePage';
import AnalyticsDashboard from './components/hr/AnalyticsDashboard';

import RoleHeader from './components/shared/RoleHeader';
import MyCandidates from './components/dept/MyCandidates';
import HeadSummary from './components/hrhead/HeadSummary';
import DirectorAnalytics from './components/hrhead/DirectorAnalytics';
import ReportPage from './components/report/ReportPage';
import Workspace from './components/employee/Workspace';
import Care from './components/employee/Care';
import Surveys from './components/employee/Surveys';
import VacancyShowcase from './components/employee/VacancyShowcase';

export type AppMode = 'portal' | 'hr' | 'head' | 'director' | 'dept' | 'employee';

const initialWorkspace = new URLSearchParams(window.location.search).get('workspace');

const MODES: { id: AppMode; label: string }[] = [
  { id: 'portal', label: 'Портал соискателя' },
  { id: 'hr', label: 'Кабинет HR-менеджера' },
  { id: 'head', label: 'Начальник ОК' },
  { id: 'director', label: 'Директор департамента кадров' },
  { id: 'dept', label: 'Руководитель департамента' },
  { id: 'employee', label: 'Сотрудник' },
];

export type PortalRoute = 'home' | 'vacancies' | 'students' | 'practice' | 'cabinet';

export const App: React.FC = () => {
  // Mode: 'portal' (Соискатель) vs 'hr' (HR-менеджер)
  const [appMode, setAppMode] = useState<AppMode>(initialWorkspace === 'support' || initialWorkspace === 'development' || initialWorkspace === 'workforce' || initialWorkspace === 'onboarding' ? 'employee' : 'portal');
  const [headTab, setHeadTab] = useState<string>('summary');
  const [directorTab, setDirectorTab] = useState<string>('analytics');
  const [employeeTab, setEmployeeTab] = useState<string>(initialWorkspace === 'support' || initialWorkspace === 'development' || initialWorkspace === 'workforce' || initialWorkspace === 'onboarding' ? initialWorkspace : 'workspace');
  const [hrAnalyticsView, setHrAnalyticsView] = useState<'dashboard' | 'report'>('dashboard');

  // Portal Routing State (Главная по умолчанию)
  const [portalRoute, setPortalRoute] = useState<PortalRoute>(initialWorkspace === 'practice' ? 'practice' : 'home');

  // HR Manager Routing State
  const [hrTab, setHrTab] = useState<HRNavTab>('database');
  const [dbView, setDbView] = useState<'list' | 'profile'>('list');
  const [databaseCandidateId, setDatabaseCandidateId] = useState('c1');
  const [hrView, setHrView] = useState<'list' | 'card'>('list');
  const [selectedResponseVacancyId] = useState<string>('v1');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>('r1');

  const handlePortalHome = () => {
    setPortalRoute('home');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePortalNav = (navId: string) => {
    if (navId === 'vacancies') {
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
      <div className="bg-[#141A24] text-white text-[12px] px-6 py-2 flex items-center justify-between z-50">
        <div className="flex items-center gap-3">
          <span className="text-[#8E939D]">Режим:</span>
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
          GorkyCode · team 9
        </div>
      </div>

      {/* ======================================================== */}
      {/* 1. ПОРТАЛ СОИСКАТЕЛЯ                                     */}
      {/* ======================================================== */}
      {appMode === 'portal' && (
        <>
          <Header
            activeNav={portalRoute === 'home' ? '' : portalRoute}
            onLogoClick={handlePortalHome}
            onNavClick={handlePortalNav}
            onLoginClick={() => {
              setPortalRoute('cabinet');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            onRegisterClick={() => {
              setPortalRoute('cabinet');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />

          <main className="flex-1 max-w-[1216px] mx-auto px-4 sm:px-6 py-6 w-full space-y-8">
            {/* ГЛАВНАЯ СТРАНИЦА ПОРТАЛА (макет 1. Главная портала.png) */}
            {portalRoute === 'home' && (
              <>
                <HeroSection />

                <CategoryCards
                  onSelectCategory={(id) => {
                    if (id === 'vacancies') setPortalRoute('vacancies');
                    else if (id === 'students') setPortalRoute('students');
                    else setPortalRoute('home');
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                />

                <NewVacanciesSection
                  onSelectVacancy={() => {
                    setPortalRoute('vacancies');
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                />

                <WhyUsSection />

                <ReserveCtaBanner />
              </>
            )}

            {/* ВАКАНСИЯ: ФОРМА ОТКЛИКА И ОТКЛИК ОТПРАВЛЕН (макеты 2 и 3) */}
            {portalRoute === 'vacancies' && (
              <VacancyPage
                onGoHome={handlePortalHome}
                onGoCabinet={() => {
                  setPortalRoute('cabinet');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* СТУДЕНТАМ: ПРАКТИКА И МЕРОПРИЯТИЯ (макет 6) */}
            {portalRoute === 'students' && (
              <StudentsPage
                onApplyPractice={() => {
                  setPortalRoute('practice');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onRegisterEvent={(title) => alert(`Запись на мероприятие: ${title}`)}
              />
            )}

            {portalRoute === 'practice' && <StudentsWorkspace />}

            {/* ЛИЧНЫЙ КАБИНЕТ КАНДИДАТА (макет 5) */}
            {portalRoute === 'cabinet' && (
              <ServiceAccess initialLogin="candidate">{(token) => <HiringWorkspace audience="candidate" token={token} />}</ServiceAccess>
            )}
          </main>
        </>
      )}

      {/* ======================================================== */}
      {/* 2. КАБИНЕТ HR-МЕНЕДЖЕРА                                 */}
      {/* ======================================================== */}
      {appMode === 'hr' && (
        <>
          <HeaderHR
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
                onSelectCandidate={(candidate: CandidateRecord) => {
                  setDatabaseCandidateId(candidate.id);
                  setDbView('profile');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* МАКЕТЫ 13–19: ПРОФИЛЬ КАНДИДАТА И ДЕЙСТВИЯ */}
            {hrTab === 'database' && dbView === 'profile' && (
              <CandidateProfile
                key={databaseCandidateId}
                candidateId={databaseCandidateId}
                onBackToDatabase={() => {
                  setDbView('list');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onOpenInterview={() => {
                  setHrTab('interview');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onOpenReserve={() => {
                  setHrTab('reserve');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* 2 & 3. ОТКЛИКИ ПО ВАКАНСИЯМ + МАКЕТЫ 4 (Загрузка) и 5 (Ошибка) */}
            {hrTab === 'vacancies' && hrView === 'list' && (
              <VacancyResponses
                initialVacancyId={selectedResponseVacancyId}
                onOpenCard={(responseId: string) => {
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
                onRequestClarification={() => alert('Запрос на уточнение отправлен')}
                onReject={() => alert('Отклонение с причиной')}
              />
            )}

            {/* 20. ТЕЛЕФОННОЕ ИНТЕРВЬЮ (макет 20. Телефонное интервью.png) */}
            {hrTab === 'interview' && (
              <TelephoneInterview
                applicationId={selectedCandidateId}
                onBackToCard={() => {
                  setHrTab('database');
                  setDbView('profile');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            )}

            {/* 24 & 25. КАДРОВЫЙ РЕЗЕРВ: КОНКУРС И СТУДЕНТЫ (макеты 24 и 25) */}
            {hrTab === 'archive' && <ArchivePage />}
            {hrTab === 'hiring' && <ServiceAccess>{(token) => <HiringWorkspace token={token} />}</ServiceAccess>}
            {hrTab === 'requirements' && <ServiceAccess>{(_token, role) => <RequirementsPage role={role === 'department' ? 'department' : 'hr'} />}</ServiceAccess>}
            {hrTab === 'reserve' && (
              <TalentReserve />
            )}

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
      {/* НАЧАЛЬНИК ОТДЕЛА КАДРОВ: Сводка / Архив кадров / Аналитика */}
      {appMode === 'head' && (
        <>
          <RoleHeader
            tabs={[
              { id: 'summary', label: 'Сводка' },
              { id: 'reserve', label: 'Архив кадров' },
              { id: 'analytics', label: 'Аналитика' },
            ]}
            activeTab={headTab}
            onTabChange={setHeadTab}
            roleLabel="Начальник отдела кадров · Ирина Б."
            onLogoClick={() => setHeadTab('summary')}
          />
          <main className="flex-1 w-full">
            {headTab === 'summary' && <HeadSummary />}
            {headTab === 'reserve' && <TalentReserve />}
            {headTab === 'analytics' && <DirectorAnalytics onExportReport={() => setAppMode('hr')} />}
          </main>
        </>
      )}

      {/* ДИРЕКТОР ДЕПАРТАМЕНТА КАДРОВ: Аналитика / Архив кадров / Единая база */}
      {appMode === 'director' && (
        <>
          <RoleHeader
            tabs={[
              { id: 'analytics', label: 'Аналитика' },
              { id: 'reserve', label: 'Архив кадров' },
              { id: 'database', label: 'Единая база' },
            ]}
            activeTab={directorTab}
            onTabChange={setDirectorTab}
            roleLabel="Директор департамента кадров · Елена В."
            onLogoClick={() => setDirectorTab('analytics')}
          />
          <main className="flex-1 w-full">
            {directorTab === 'analytics' && (
              <DirectorAnalytics
                onExportReport={() => {
                  setHrTab('analytics');
                  setHrAnalyticsView('report');
                  setAppMode('hr');
                }}
              />
            )}
            {directorTab === 'reserve' && <TalentReserve />}
            {directorTab === 'database' && <CandidatesDatabase onSelectCandidate={() => {}} />}
          </main>
        </>
      )}

      {/* РУКОВОДИТЕЛЬ ДЕПАРТАМЕНТА: Мои кандидаты */}
      {appMode === 'dept' && (
        <>
          <RoleHeader
            tabs={[{ id: 'mine', label: 'Мои кандидаты' }]}
            activeTab="mine"
            onTabChange={() => {}}
            roleLabel="Директор департамента цифрового развития · Андрей Г."
          />
          <main className="flex-1 w-full">
            <MyCandidates />
          </main>
        </>
      )}

      {/* СОТРУДНИК ДЕПАРТАМЕНТА */}
      {appMode === 'employee' && (
        <>
          <RoleHeader
            tabs={[
              { id: 'workspace', label: 'Рабочее пространство' },
              { id: 'care', label: 'Забота и мотивация' },
              { id: 'support', label: 'Материальная помощь' },
              { id: 'surveys', label: 'Опросы' },
              { id: 'vacancies', label: 'Витрина вакансий' },
            ]}
            activeTab={employeeTab}
            onTabChange={setEmployeeTab}
            roleLabel={employeeTab === 'support' || employeeTab === 'development' ? 'Личный кабинет' : 'Специалист департамента экономики · Кирилл Л.'}
            onLogoClick={() => setEmployeeTab('workspace')}
          />
          <main className="flex-1 w-full">
            {employeeTab === 'workspace' && <Workspace onNavigate={setEmployeeTab} />}
            {employeeTab === 'care' && <Care />}
            {employeeTab === 'support' && <SupportPage />}
            {employeeTab === 'development' && <DevelopmentPage />}
            {employeeTab === 'workforce' && <WorkforcePage />}
            {employeeTab === 'onboarding' && <WorkforcePage initialTab="onboarding" />}
            {employeeTab === 'surveys' && <Surveys />}
            {employeeTab === 'vacancies' && <VacancyShowcase />}
          </main>
        </>
      )}
    </div>
  );
};

export default App;
