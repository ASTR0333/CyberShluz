import { useEffect, useState, type ReactNode } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import {
  Box,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Monitor,
  MonitorPlay,
  Settings,
  X,
} from 'lucide-react';
import { LabLaunch } from './pages/LabLaunch';
import { StandStatus } from './pages/StandStatus';
import { TeacherDashboard } from './pages/TeacherDashboard';
import { AdminSettings } from './pages/AdminSettings';
import { Login } from './pages/Login';
import { mockApi, authApi, getAuth, saveAuth, clearAuth, type AuthInfo } from './api/mocks';
import { ErrorBoundary } from './components/ErrorBoundary';
import cyberLogo from './assets/cyberprotect-logo.svg';







function LtiGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ltiToken = params.get('lti_token');
    if (!ltiToken) { setReady(true); return; }

    let alive = true;
    (async () => {
      try {

        saveAuth({ access_token: ltiToken, username: '', role: 'student', display_name: '', user_id: 0 });
        const me = await authApi.me();
        saveAuth({
          access_token: ltiToken,
          username: me.username,
          role: (me.role as 'student' | 'teacher' | 'admin') || 'student',
          display_name: me.display_name || me.username,
          user_id: me.user_id,
        });
      } catch {
        clearAuth();
      }
      if (!alive) return;
      params.delete('lti_token');
      const qs = params.toString();
      navigate(location.pathname + (qs ? `?${qs}` : ''), { replace: true });
      setReady(true);
    })();
    return () => { alive = false; };

  }, [location.pathname, location.search, navigate]);

  if (!ready) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-cyber-blue" />
      </div>
    );
  }
  return <>{children}</>;
}

function StatusNavLink() {
  const navigate = useNavigate();
  const location = useLocation();

  const target = '/status/my';
  const isActive = location.pathname.startsWith('/status/');

  return (
    <button
      onClick={() => navigate(target)}
      className={`w-full min-h-11 flex items-center px-5 py-2.5 transition-colors text-sm font-medium text-left border-l-[3px]
        ${isActive
          ? 'bg-[#EAF1F8] text-cyber-blue-dark border-cyber-blue-accent'
          : 'text-cyber-gray-dark hover:bg-[#F3F6F9] hover:text-cyber-blue-dark border-transparent'}
      `}
    >
      <Monitor className={`w-[18px] h-[18px] mr-3 ${isActive ? 'text-cyber-blue-accent' : 'text-cyber-gray-light'}`} strokeWidth={1.8} />
      Мой стенд
    </button>
  );
}

const navItemClass = (isActive: boolean) =>
  `min-h-11 flex items-center px-5 py-2.5 transition-colors text-sm font-medium border-l-[3px]
   ${isActive
     ? 'bg-[#EAF1F8] text-cyber-blue-dark border-cyber-blue-accent'
     : 'text-cyber-gray-dark hover:bg-[#F3F6F9] hover:text-cyber-blue-dark border-transparent'}`;

function CapacityBadge() {
  const [util, setUtil] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const auth = getAuth();
  const canFetch = auth?.role === 'teacher' || auth?.role === 'admin';

  useEffect(() => {
    if (!canFetch) return;
    let alive = true;
    const tick = async () => {
      try {
        const c = await mockApi.getCapacity();
        if (!alive) return;
        setUtil(c.utilization_pct);
        setOver(c.over_threshold);
      } catch {
        if (alive) setUtil(null);
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [canFetch]);

  if (!canFetch) return null;

  if (util === null) {
    return (
      <span className="hidden md:inline-flex items-center gap-2 text-[11px] font-semibold text-cyber-gray-light bg-cyber-gray-surface border border-cyber-gray-border px-2.5 py-1 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-cyber-gray-light" />
        Проверка кластера…
      </span>
    );
  }

  const palette = over
    ? 'text-red-700 bg-red-50 border-red-100'
    : util > 60
      ? 'text-amber-700 bg-amber-50 border-amber-100'
      : 'text-emerald-700 bg-emerald-50 border-emerald-100';
  const dot = over ? 'bg-red-500' : util > 60 ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <span className={`hidden md:inline-flex items-center gap-2 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${palette}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      Кластер КИ: {util}%
    </span>
  );
}

function UserMenu({ auth }: { auth: AuthInfo }) {
  const navigate = useNavigate();
  const onLogout = () => {
    clearAuth();
    navigate('/login', { replace: true });
  };



  const cleanName = auth.display_name.replace(/^lti:/, '').trim();
  const showName = cleanName.length > 0 && !/^\d+$/.test(cleanName);

  return (
    <div className="flex items-center gap-3 sm:gap-4">
      <div className="flex items-center gap-2 text-cyber-blue-dark text-sm font-medium">
        {showName && <span className="hidden sm:inline">{cleanName}</span>}
        <span className="hidden min-[360px]:inline-flex text-[10px] px-2 py-1 rounded-full bg-[#E7F2FB] text-cyber-blue font-bold uppercase tracking-wider">
          {auth.role === 'student' ? 'Студент' : auth.role === 'teacher' ? 'Преподаватель' : 'Администратор'}
        </span>
      </div>
      <button
        onClick={onLogout}
        title="Выйти"
        className="w-9 h-9 rounded-full border border-cyber-gray-border flex items-center justify-center text-cyber-blue hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
}

function ProtectedLayout({ auth, children }: { auth: AuthInfo; children: React.ReactNode }) {
  const isStudent = auth.role === 'student';
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="h-screen w-full flex flex-col font-sans text-cyber-gray-dark overflow-hidden bg-cyber-gray-surface">
      <div className="h-1 flex-shrink-0 bg-cyber-blue-accent" />
      <header className="bg-white border-b border-cyber-gray-border h-20 flex-shrink-0 px-4 sm:px-6 flex justify-between items-center z-30 shadow-[0_2px_8px_rgba(0,32,77,0.04)]">
        <div className="flex items-center gap-3 sm:gap-5 min-w-0">
          <button
            type="button"
            onClick={() => setNavOpen((value) => !value)}
            className="lg:hidden w-10 h-10 -ml-1 rounded-brand border border-cyber-gray-border flex items-center justify-center text-cyber-blue-dark"
            aria-label={navOpen ? 'Закрыть навигацию' : 'Открыть навигацию'}
            aria-expanded={navOpen}
          >
            {navOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <img src={cyberLogo} alt="КИБЕРПРОТЕКТ" className="h-9 sm:h-10 w-auto max-w-[194px] sm:max-w-[215px] select-none" />
          <div className="h-8 w-px bg-cyber-gray-border hidden md:block" />
          <span className="hidden xl:inline text-xs font-semibold text-cyber-gray-light">Учебная оркестрация</span>
          <CapacityBadge />
        </div>
        <UserMenu auth={auth} />
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        <nav className="hidden lg:flex w-16 bg-cyber-blue-dark flex-shrink-0 flex-col items-center z-10">
          <div className="w-full flex flex-col items-center gap-2">
            <div className="w-full h-16 flex items-center justify-center text-white bg-cyber-blue border-l-[3px] border-cyber-blue-light" title="Киберполигон">
              <Box className="w-5 h-5" strokeWidth={1.8} />
            </div>
          </div>
        </nav>

        {navOpen && (
          <button
            type="button"
            className="absolute inset-0 bg-cyber-blue-dark/35 z-10 lg:hidden"
            onClick={() => setNavOpen(false)}
            aria-label="Закрыть навигацию"
          />
        )}

        <aside className={`${navOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 absolute lg:static inset-y-0 left-0 w-[min(19rem,86vw)] lg:w-64 bg-white border-r border-cyber-gray-border flex-shrink-0 flex flex-col z-20 transition-transform duration-200 shadow-2xl lg:shadow-none`}>
          <div className="px-5 py-5 border-b border-cyber-gray-border">
            <h2 className="text-base font-bold text-cyber-blue-dark">Киберполигон</h2>
            <p className="text-xs text-cyber-gray-light mt-1">Управление учебными стендами</p>
          </div>

          <div className="flex-1 overflow-y-auto py-4">
            <p className="px-5 mb-2 text-[11px] font-semibold text-cyber-gray-light">Основное</p>
            {!isStudent && (
              <NavLink to="/" className={({ isActive }) => navItemClass(isActive)} end>
                <LayoutDashboard className="w-[18px] h-[18px] mr-3" strokeWidth={1.8} />
                Мониторинг
              </NavLink>
            )}

            <NavLink to="/launch" className={({ isActive }) => navItemClass(isActive)}>
              <MonitorPlay className="w-[18px] h-[18px] mr-3" strokeWidth={1.8} />
              Запуск стенда
            </NavLink>

            <StatusNavLink />

            {!isStudent && (
              <>
                <div className="mt-6 mb-2 px-5">
                  <p className="text-[11px] text-cyber-gray-light font-semibold">Система</p>
                </div>
                <NavLink to="/admin" className={({ isActive }) => navItemClass(isActive)}>
                  <Settings className="w-[18px] h-[18px] mr-3" strokeWidth={1.8} />
                  Администрирование
                </NavLink>
              </>
            )}
          </div>
        </aside>

        <main className="flex-1 min-w-0 brand-surface overflow-y-auto">
          <div className="p-4 sm:p-6 xl:p-8 max-w-7xl mx-auto min-h-full">{children}</div>
        </main>
      </div>
    </div>
  );
}

function RequireAuth({ children, role }: { children: React.ReactNode; role?: 'teacher' }) {
  const auth = getAuth();
  if (!auth) return <Navigate to="/login" replace />;
  if (role === 'teacher' && auth.role === 'student') {
    return <Navigate to="/status/my" replace />;
  }
  return <ProtectedLayout auth={auth}>{children}</ProtectedLayout>;
}

function RootRedirect() {
  const auth = getAuth();
  if (!auth) return <Navigate to="/login" replace />;
  if (auth.role === 'student') return <Navigate to="/status/my" replace />;

  return (
    <ProtectedLayout auth={auth}>
      <TeacherDashboard />
    </ProtectedLayout>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        reverseOrder={false}
        toastOptions={{
          style: {
            borderRadius: '10px',
            background: '#00204D',
            color: '#fff',
            fontSize: '13px',
          },
        }}
      />

      <LtiGate>
      <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RootRedirect />} />
        <Route
          path="/launch"
          element={
            <RequireAuth>
              <LabLaunch />
            </RequireAuth>
          }
        />
        <Route
          path="/status/my"
          element={
            <RequireAuth>
              <StandStatus />
            </RequireAuth>
          }
        />
        <Route
          path="/status/:stand_id"
          element={
            <RequireAuth>
              <StandStatus />
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth role="teacher">
              <AdminSettings />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
      </LtiGate>
    </BrowserRouter>
  );
}

export default App;
