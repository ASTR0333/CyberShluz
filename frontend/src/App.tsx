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
import { Loader2 } from 'lucide-react';
import { LabLaunch } from './pages/LabLaunch';
import { StandStatus } from './pages/StandStatus';
import { TeacherDashboard } from './pages/TeacherDashboard';
import { AdminSettings } from './pages/AdminSettings';
import { Login } from './pages/Login';
import { LayoutDashboard, Rocket, Activity, Settings, LogOut, Box } from 'lucide-react';
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
      className={`w-full flex items-center px-4 py-2.5 rounded-none transition-colors text-sm font-medium text-left
        ${isActive
          ? 'bg-blue-50 text-cyber-blue-accent border-l-2 border-cyber-blue-accent'
          : 'text-cyber-gray-dark hover:bg-white hover:text-cyber-blue border-l-2 border-transparent'}
      `}
    >
      <Activity className={`w-4 h-4 mr-3 ${isActive ? 'text-cyber-blue-accent' : 'text-cyber-gray-light'}`} />
      Мой стенд
    </button>
  );
}

const navItemClass = (isActive: boolean) =>
  `flex items-center px-4 py-2.5 transition-colors text-sm font-medium border-l-2
   ${isActive
     ? 'bg-blue-50/50 text-cyber-blue-accent border-cyber-blue-accent'
     : 'text-cyber-gray-dark hover:bg-white hover:text-cyber-blue border-transparent'}`;

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
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2 text-cyber-blue-accent text-sm font-medium">
        {showName && <span className="hidden sm:inline">{cleanName}</span>}
        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyber-blue-accent/10 text-cyber-blue-accent font-bold uppercase tracking-wider">
          {auth.role === 'student' ? 'Студент' : 'Админ'}
        </span>
      </div>
      <button
        onClick={onLogout}
        title="Выйти"
        className="w-8 h-8 rounded-full border border-cyber-gray-border flex items-center justify-center text-cyber-blue hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
}

function ProtectedLayout({ auth, children }: { auth: AuthInfo; children: React.ReactNode }) {
  const isStudent = auth.role === 'student';

  return (
    <div className="h-screen w-full flex flex-col font-sans text-cyber-gray-dark overflow-hidden">

      <header className="bg-white border-b border-cyber-gray-border h-14 flex-shrink-0 px-6 flex justify-between items-center z-20">
        <div className="flex items-center gap-6">
          <img src={cyberLogo} alt="КИБЕРПРОТЕКТ" className="h-8 w-auto select-none" />
          <div className="h-6 w-px bg-cyber-gray-border hidden md:block" />
          <CapacityBadge />
        </div>
        <UserMenu auth={auth} />
      </header>


      <div className="flex-1 flex overflow-hidden">

        <nav className="w-14 bg-[#141f36] flex-shrink-0 flex flex-col items-center py-4 z-10">
          <div className="w-full flex flex-col items-center gap-2">
            <div className="w-full h-12 flex items-center justify-center text-white bg-[#214389]/40 border-l-2 border-[#5382e6] transition-colors relative group" title="Оркестрация">
              <Box className="w-5 h-5" />
            </div>
          </div>
        </nav>


        <div className="w-64 bg-cyber-gray-surface border-r border-cyber-gray-border flex-shrink-0 flex flex-col z-0">
          <div className="px-5 py-5">
            <h2 className="text-lg font-normal text-cyber-gray-dark">Оркестрация</h2>
          </div>

          <div className="flex-1 overflow-y-auto">
            {!isStudent && (
              <NavLink to="/" className={({ isActive }) => navItemClass(isActive)} end>
                <LayoutDashboard className="w-4 h-4 mr-3" />
                Панель управления
              </NavLink>
            )}

            <NavLink to="/launch" className={({ isActive }) => navItemClass(isActive)}>
              <Rocket className="w-4 h-4 mr-3" />
              Запуск стенда
            </NavLink>

            <StatusNavLink />

            {!isStudent && (
              <>
                <div className="mt-6 mb-2 px-5">
                  <p className="text-[11px] text-cyber-gray-light uppercase tracking-wider font-semibold">Администрирование</p>
                </div>
                <NavLink to="/admin" className={({ isActive }) => navItemClass(isActive)}>
                  <Settings className="w-4 h-4 mr-3" />
                  Стенд админа
                </NavLink>
              </>
            )}
          </div>
        </div>


        <main className="flex-1 bg-white overflow-y-auto">
          <div className="p-8 max-w-7xl mx-auto min-h-full">{children}</div>
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
            borderRadius: '6px',
            background: '#141f36',
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
