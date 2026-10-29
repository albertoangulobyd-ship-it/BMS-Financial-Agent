// La entrada del bundle. Antes de pintar nada, el nonce de estilos de esta pagina: el
// servidor lo pone en la CSP (style-src 'nonce-...') y en <meta name="bms-nonce">, y las
// pocas bibliotecas que meten un <style> (el bloqueo de scroll de los menus y la hoja del
// movil, react-remove-scroll) lo usan via get-nonce. Sin el, la CSP las bloquearia; con
// 'unsafe-inline' cualquier estilo inyectado pasaria.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { setNonce } from 'get-nonce';
// Primero el CSS de la app: declara el orden de las capas (theme, base, components,
// utilities) antes que las hojas de Aurora que importan los componentes.
import './index.css';
import { App } from './App';
import { trackModality } from './lib/modality';
import { stickServerBands } from './lib/server-bands';
import { DEVICE_THEME_KEY, loadTheme } from './lib/storage';
import { DEFAULT_THEME, applyInitialTheme } from './lib/theme';

function pageNonce(): string | undefined {
  const value = document.querySelector('meta[name="bms-nonce"]')?.getAttribute('content') ?? '';
  return /^[A-Za-z0-9_-]{16,128}$/.test(value) ? value : undefined;
}

const nonce = pageNonce();
if (nonce) setNonce(nonce);

// El tema antes de la primera pintura (index.html ya trae el oscuro, el de por defecto).
applyInitialTheme(loadTheme(DEVICE_THEME_KEY) ?? DEFAULT_THEME);
// Las bandas del servidor, a la vista al desplazar la pagina (y la cabecera, debajo).
stickServerBands();
// Con que se mueve la persona (teclado o raton), para el foco que solo se ve con el teclado.
trackModality();

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}
