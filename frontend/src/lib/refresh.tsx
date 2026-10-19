// Despues de una orden cambian mas cosas que la ficha: las cuentas de la navegacion, las
// listas y el Overzicht. Una version comun que sube con cada orden hecha; quien lee algo
// la pone en sus dependencias y vuelve a leer. Sin temporizadores ni sondeos.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

interface RefreshValue {
  version: number;
  bump: () => void;
}

const RefreshContext = createContext<RefreshValue>({ version: 0, bump: () => undefined });

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const value = useMemo(() => ({ version, bump }), [version, bump]);
  return <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>;
}

export function useRefresh(): RefreshValue {
  return useContext(RefreshContext);
}
