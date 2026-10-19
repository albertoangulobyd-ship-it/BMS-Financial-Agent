// La entrada: la persona escribe su token personal (el mismo de la consola). Una frase
// dice que es y quien lo da. El token no se guarda en ningun sitio del navegador: si la
// entrada sale bien vive en la memoria de la sesion; si no, se borra del campo.
//
// Por eso no hay <form> ni <input type="password">: Edge y Chromium no hacen caso de
// autocomplete="off" para guardar contrasenas, y un campo de contrasena que desaparece
// despues de un fetch es para ellos una entrada que salio bien, asi que ofrecerian guardar
// el token en su gestor (y de ahi sincronizarlo con la cuenta de Microsoft). Es un campo de
// texto con los caracteres tapados (-webkit-text-security), autocomplete="one-time-code"
// (que no se ofrece guardar), Intro para entrar y el campo vaciado antes de comprobarlo.
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useT, type Messages } from '@/i18n';
import { ApiError } from '@/lib/api';
import { useSession } from '@/lib/session';
import { LanguageSwitch } from '@/shell/language-switch';

// Lo que se guarda es la clave del texto, no el texto: al cambiar de idioma, cambia.
type LoginErrorKey = 'empty' | 'invalid' | 'forbidden' | 'incompatible' | 'unreachable';

function loginError(error: unknown): LoginErrorKey {
  if (error instanceof ApiError) {
    if (error.kind === 'unauthorized') return 'invalid';
    if (error.kind === 'forbidden') return 'forbidden';
    if (error.kind === 'incompatible') return 'incompatible';
  }
  return 'unreachable';
}

function errorText(key: LoginErrorKey, t: Messages): string {
  return t.login[key];
}

export function LoginScreen() {
  const { t } = useT();
  const { login, notice } = useSession();
  const [token, setToken] = useState('');
  const [error, setError] = useState<LoginErrorKey | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const helpId = useId();
  const errorId = useId();

  useEffect(() => {
    document.title = t.app.name;
    inputRef.current?.focus();
  }, [t]);

  async function submit() {
    if (busy) return;
    const value = token.trim();
    if (!value) {
      setError('empty');
      return;
    }
    // Fuera del campo antes de comprobarlo: si sale bien, la pantalla se va sin el token
    // dentro; si no, la persona lo vuelve a escribir.
    setToken('');
    setBusy(true);
    setError(null);
    try {
      await login(value);
    } catch (e) {
      setError(loginError(e));
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      void submit();
    }
  }

  const noticeText =
    notice === 'sessionEnded' ? t.login.sessionEnded : notice === 'loggedOut' ? t.login.loggedOut : null;

  return (
    <div className='flex h-full items-center justify-center overflow-auto bg-background px-4 py-10'>
      <main className='w-full max-w-[26rem]'>
        <div className='mb-8 flex items-center justify-between gap-4'>
          <div className='flex items-center gap-3'>
            <span
              aria-hidden='true'
              className='flex h-9 w-9 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground'
            >
              BM
            </span>
            <div className='leading-tight'>
              <p className='text-[15px] font-semibold'>{t.app.name}</p>
              <p className='text-xs text-muted-foreground'>{t.app.company}</p>
            </div>
          </div>
          <LanguageSwitch />
        </div>

        <div className='rounded-md border border-border bg-card px-6 py-6'>
          <h1 className='text-[21px] font-semibold leading-tight'>{t.login.title}</h1>
          <p className='mt-1 text-muted-foreground'>{t.login.intro}</p>

          {noticeText && (
            <p role='status' className='mt-4 rounded-md border border-border bg-muted px-3 py-2'>
              {noticeText}
            </p>
          )}

          <div className='mt-5 flex flex-col gap-3'>
            <Label htmlFor='token'>{t.login.tokenLabel}</Label>
            <Input
              id='token'
              ref={inputRef}
              type='text'
              autoComplete='one-time-code'
              autoCapitalize='off'
              autoCorrect='off'
              spellCheck={false}
              data-lpignore='true'
              data-1p-ignore='true'
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={onKeyDown}
              aria-describedby={error ? `${errorId} ${helpId}` : helpId}
              aria-invalid={error ? true : undefined}
              className='font-mono [-webkit-text-security:disc]'
            />
            <p id={helpId} className='text-xs leading-relaxed text-muted-foreground'>
              {t.login.tokenHelp}
            </p>
            {error && (
              <p id={errorId} role='alert' className='text-sm font-medium text-late-foreground'>
                {errorText(error, t)}
              </p>
            )}
            <Button id='login-submit' type='button' disabled={busy} className='mt-1' onClick={() => void submit()}>
              <KeyRound className='mr-2 h-4 w-4' aria-hidden='true' />
              {busy ? t.login.checking : t.login.submit}
            </Button>
          </div>
          <p className='mt-4 text-xs text-muted-foreground'>{t.login.neverStored}</p>
        </div>
      </main>
    </div>
  );
}
