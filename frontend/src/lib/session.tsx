// La sesion: quien ha entrado, con que permisos y en que entorno. El token vive solo en
// memoria, dentro del cliente de la API de esta sesion: no va a localStorage, ni a
// sessionStorage, ni a una cookie, ni a la URL. Salir (o un 401) tira el cliente y con
// el el token.
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { createApiClient, paths, type ApiClient, type Environment, type Me } from './api';

export interface Session {
  api: ApiClient;
  me: Me;
  environment: Environment;
}

/** Por que se ve la pantalla de entrada: nada, salio la persona o caduco la sesion. */
export type LoginNotice = 'loggedOut' | 'sessionEnded' | null;

interface SessionValue {
  session: Session | null;
  notice: LoginNotice;
  login: (token: string) => Promise<Session>;
  logout: (notice?: LoginNotice) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({
  children,
  onLogin,
}: {
  children: ReactNode;
  /** Lo que hace la app al entrar alguien (sus preferencias). */
  onLogin?: (session: Session) => void;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState<LoginNotice>(null);
  // El cliente de la sesion en curso: un 401 que llega tarde de una sesion anterior no
  // echa a la persona que acaba de entrar.
  const currentApi = useRef<ApiClient | null>(null);

  const logout = useCallback((reason: LoginNotice = 'loggedOut') => {
    currentApi.current?.dispose();
    currentApi.current = null;
    setSession(null);
    setNotice(reason);
  }, []);

  const login = useCallback(
    async (token: string) => {
      const api: ApiClient = createApiClient({
        token,
        // Un 401 en cualquier pantalla: fuera, con el aviso de que la sesion termino.
        // Durante la entrada no: ahi es que el token no vale, y lo dice la entrada.
        onUnauthorized: () => {
          if (currentApi.current === api) logout('sessionEnded');
        },
      });
      let me: Me;
      try {
        me = await api.get<Me>(paths.me);
      } catch (error) {
        api.dispose();
        throw error;
      }
      currentApi.current?.dispose();
      currentApi.current = api;
      // El entorno lo dice la cabecera X-BMS-Entorno de esa misma respuesta.
      const next: Session = { api, me, environment: api.environment };
      setNotice(null);
      setSession(next);
      onLogin?.(next);
      return next;
    },
    [logout, onLogin]
  );

  const value = useMemo(() => ({ session, notice, login, logout }), [session, notice, login, logout]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used within SessionProvider');
  return value;
}

/** Si la persona tiene un permiso: la navegacion y los botones lo siguen. */
export function useCan(): (permission: string | null | undefined) => boolean {
  const { session } = useSession();
  return useCallback(
    (permission) => !permission || Boolean(session?.me.permisos.includes(permission)),
    [session]
  );
}

/** El papel en palabras, para el menu de la persona (no hay roles en /api/v2/yo). */
export function roleOf(permissions: readonly string[]): 'admin' | 'staff' | 'readOnly' {
  if (permissions.includes('admin')) return 'admin';
  if (permissions.some((p) => p !== 'ver_facturas')) return 'staff';
  return 'readOnly';
}
