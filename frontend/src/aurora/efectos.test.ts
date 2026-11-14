// Lo que devuelve un efecto de React es su limpieza: React lo llama al desmontar, sea lo que sea.
// `useEffect(() => nodo.scrollIntoView())` devolvia `undefined` hasta que Chromium (153) empezo a
// devolver una promesa en scrollIntoView, scrollTo y scrollBy: al desmontarse el componente, React
// llamaba a la promesa («P is not a function») y la app entera se quedaba en blanco. TypeScript no
// lo ve (para lib.dom esas llamadas aun son `void`), asi que lo mira esta prueba, en las fuentes:
// un efecto sin llaves solo puede ser una funcion que devuelve su limpieza, y con llaves no
// devuelve el resultado de una llamada del DOM.
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const SRC = fileURLToPath(new URL('..', import.meta.url));
const EFFECTS = new Set(['useEffect', 'useLayoutEffect', 'useInsertionEffect']);

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) return sources(path);
    return /\.tsx?$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

function isFunction(node: ts.Node): node is ts.ArrowFunction | ts.FunctionExpression {
  return ts.isArrowFunction(node) || ts.isFunctionExpression(node);
}

// Llamadas del DOM que no devuelven una limpieza: `void` para lib.dom, y una promesa (las de
// desplazar, play, requestFullscreen) o nada en el navegador.
const DOM_CALLS = new Set(['scrollIntoView', 'scrollTo', 'scrollBy', 'scroll', 'focus', 'blur', 'click', 'showModal', 'show', 'close', 'play', 'pause', 'requestFullscreen', 'animate']);

/** Lo que un `return` de un efecto puede llevar: nada, `undefined`, una funcion, un nombre, o lo
 *  que devuelve una funcion nuestra que monta algo y da su limpieza (`return mountFinanceBento(…)`). */
function allowedReturn(node: ts.Expression | undefined): boolean {
  if (!node) return true;
  if (ts.isParenthesizedExpression(node) || ts.isNonNullExpression(node)) return allowedReturn(node.expression);
  if (ts.isCallExpression(node)) return !(ts.isPropertyAccessExpression(node.expression) && DOM_CALLS.has(node.expression.name.text));
  return isFunction(node) || ts.isIdentifier(node) || node.kind === ts.SyntaxKind.VoidExpression;
}

/** Los `return` del propio efecto, sin entrar en las funciones de dentro. */
function ownReturns(body: ts.Node, found: ts.ReturnStatement[] = []): ts.ReturnStatement[] {
  ts.forEachChild(body, (child) => {
    if (ts.isReturnStatement(child)) found.push(child);
    else if (!ts.isFunctionLike(child)) ownReturns(child, found);
  });
  return found;
}

function badEffects(file: string, text: string): string[] {
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const bad: string[] = [];
  const at = (node: ts.Node) => `${file}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node)) {
      const callee = ts.isPropertyAccessExpression(node.expression) ? node.expression.name.text : ts.isIdentifier(node.expression) ? node.expression.text : '';
      const effect = node.arguments[0];
      if (EFFECTS.has(callee) && effect && isFunction(effect)) {
        if (effect.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)) bad.push(`${at(effect)} (async)`);
        else if (!ts.isBlock(effect.body)) {
          if (!isFunction(effect.body)) bad.push(`${at(effect)} (sin llaves)`);
        } else {
          for (const r of ownReturns(effect.body)) if (!allowedReturn(r.expression)) bad.push(`${at(r)} (return de una llamada del DOM)`);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return bad;
}

describe('los efectos de React', () => {
  it('la prueba ve los tres casos y deja pasar los buenos', () => {
    const sample = [
      'useEffect(() => ref.current?.scrollIntoView({ block: "nearest" }), [text]);',
      'React.useLayoutEffect(() => { if (a) return; return window.scrollTo(0, 0); }, []);',
      'useEffect(async () => { await x(); }, []);',
      'useEffect(() => () => clearTimeout(timer.current), []);',
      'useEffect(() => { ref.current?.scrollIntoView(); }, []);',
      'useEffect(() => { const t = setTimeout(() => { return f(); }, 1); return () => clearTimeout(t); }, []);',
      'useEffect(() => { if (!a) return undefined; return stop; }, []);',
      'useEffect(() => { const el = ref.current; if (!el) return; return mountFinanceBento(el, {}); }, []);',
    ].join('\n');
    expect(badEffects('muestra.tsx', sample)).toEqual(['muestra.tsx:1 (sin llaves)', 'muestra.tsx:2 (return de una llamada del DOM)', 'muestra.tsx:3 (async)']);
  });

  it('ninguno devuelve lo que da una llamada del DOM', () => {
    const files = sources(SRC.replace(/\/$/, ''));
    expect(files.length).toBeGreaterThan(40);
    const withEffects = files.filter((f) => /use(Layout|Insertion)?Effect\(/.test(readFileSync(f, 'utf8')));
    expect(withEffects.length).toBeGreaterThan(10);
    expect(files.flatMap((f) => badEffects(f.slice(SRC.length), readFileSync(f, 'utf8')))).toEqual([]);
  });
});
