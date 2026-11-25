// La tarjeta del buzon, pintada en el servidor (react-dom/server, como status-pill.test.ts): lo
// que pone quien manda el correo (remitente, asunto, nombres de los adjuntos) sale como texto,
// con data-proper-name y SIEMPRE con la etiqueta "niet gecontroleerd" (§13 S12). La revision del
// paso 12 quito la etiqueta de mailbox-card.tsx y ninguna prueba lo vio: esta si.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider, MESSAGES, type Lang } from '@/i18n';
import type { MailMessage } from '@/lib/api-types';
import { MailItem } from './mailbox-card';

function message(extra: Partial<MailMessage> = {}): MailMessage {
  return {
    mensaje_id: 9,
    recibido_en: '2026-11-24T07:00:00+00:00',
    carpeta: 'bandeja',
    remitente_doc: 'facturen@leverancier.example',
    asunto_doc: 'Factuur 118',
    adjuntos: [{ nombre_doc: 'factuur.pdf', resultado: 'documento', bytes: 120_000, documento_id: 31 }],
    ...extra,
  };
}

function render(m: MailMessage, lang: Lang = 'nl'): string {
  return renderToStaticMarkup(createElement(I18nProvider, { lang, setLang: () => {}, children: createElement(MailItem, { message: m, advice: true }) }));
}

/** Cuantas etiquetas "niet gecontroleerd" lleva el HTML. */
function tags(html: string): number {
  return html.split('class="mail-tag"').length - 1;
}

describe('un correo en la tarjeta del buzon', () => {
  it('el remitente y el asunto llevan cada uno su etiqueta "niet gecontroleerd", en cada idioma', () => {
    for (const lang of ['nl', 'en', 'es'] as const) {
      const html = render(message(), lang);
      expect(tags(html), lang).toBe(2);
      expect(html).toContain(`>${MESSAGES[lang].aurora.mailbox.unverified}<`);
      expect(html).toContain(`title="${MESSAGES[lang].aurora.mailbox.unverifiedHelp}"`);
    }
    // Sin asunto ni remitente, tambien: la etiqueta no depende de que haya texto.
    const empty = render(message({ remitente_doc: null, asunto_doc: null }));
    expect(tags(empty)).toBe(2);
    expect(empty).toContain(MESSAGES.nl.aurora.mailbox.noSubject);
  });

  it('lo que pone quien manda el correo va como texto y como nombre propio, nunca como HTML', () => {
    const html = render(
      message({
        remitente_doc: '<img src=x onerror=alert(1)>@evil.example',
        asunto_doc: '<script>alert(2)</script> Betaal nu naar NL00BANK0123456789',
        adjuntos: [{ nombre_doc: '<b>factuur</b>.pdf', resultado: 'xml', bytes: 10, documento_id: null }],
      })
    );
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;@evil.example');
    expect(html).toContain('&lt;script&gt;alert(2)&lt;/script&gt;');
    // Remitente, asunto y adjunto, cada uno con data-proper-name (no es texto de la app).
    expect(html.split('data-proper-name=""').length - 1).toBe(3);
    expect(tags(html)).toBe(2);
  });
});
