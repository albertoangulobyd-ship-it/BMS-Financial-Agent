// La entrada del bundle. Antes de pintar nada, el nonce de estilos de esta pagina: el
// servidor lo pone en la CSP (style-src 'nonce-...') y en <meta name="bms-nonce">, y las
// pocas bibliotecas que meten un <style> (el bloqueo de scroll de los menus y la hoja del
// movil, react-remove-scroll) lo usan via get-nonce. Sin el, la CSP las bloquearia; con
// 'unsafe-inline' cualquier estilo inyectado pasaria.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { setNonce } from 'get-nonce';
import { App } from './App';
import './index.css';

function pageNonce(): string | undefined {
  const value = document.querySelector('meta[name="bms-nonce"]')?.getAttribute('content') ?? '';
  return /^[A-Za-z0-9_-]{16,128}$/.test(value) ? value : undefined;
}

const nonce = pageNonce();
if (nonce) setNonce(nonce);

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App nonce={nonce} />
    </StrictMode>
  );
}
