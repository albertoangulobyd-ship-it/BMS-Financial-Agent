// Leer un PNG en Node sin dependencias (zlib de Node): lo justo para comparar los recortes de la
// escena de la suricata con los de Aurora (e2e/aurora/suricata). Solo PNG de 8 bits por canal, sin
// entrelazar, en RGB o RGBA (los de las capturas de Playwright y los de ffmpeg).
import { inflateSync } from 'node:zlib';

export interface Bitmap {
  width: number;
  height: number;
  /** RGBA, fila a fila. */
  data: Uint8Array;
}

export function decodePng(buffer: Buffer): Bitmap {
  if (buffer.readUInt32BE(0) !== 0x89504e47) throw new Error('no es un PNG');
  let offset = 8;
  let width = 0,
    height = 0,
    channels = 0;
  const parts: Buffer[] = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('latin1', offset + 4, offset + 8);
    const body = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      const depth = body[8],
        color = body[9],
        interlace = body[12];
      if (depth !== 8 || interlace !== 0 || (color !== 2 && color !== 6)) throw new Error(`PNG no admitido (bits ${depth}, color ${color}, entrelazado ${interlace})`);
      channels = color === 6 ? 4 : 3;
    } else if (type === 'IDAT') parts.push(body);
    else if (type === 'IEND') break;
    offset += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(parts));
  const stride = width * channels;
  const pixels = new Uint8Array(stride * height);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)]!;
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x += 1) {
      const a = x >= channels ? pixels[y * stride + x - channels]! : 0;
      const b = y > 0 ? pixels[(y - 1) * stride + x]! : 0;
      const c = x >= channels && y > 0 ? pixels[(y - 1) * stride + x - channels]! : 0;
      const p = a + b - c;
      const [pa, pb, pc] = [Math.abs(p - a), Math.abs(p - b), Math.abs(p - c)];
      const paeth = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      const value = line[x]! + [0, a, b, (a + b) >> 1, paeth][filter]!;
      pixels[y * stride + x] = value & 0xff;
    }
  }
  if (channels === 4) return { width, height, data: pixels };
  const data = new Uint8Array(width * height * 4);
  for (let i = 0, j = 0; i < pixels.length; i += 3, j += 4) {
    data[j] = pixels[i]!;
    data[j + 1] = pixels[i + 1]!;
    data[j + 2] = pixels[i + 2]!;
    data[j + 3] = 255;
  }
  return { width, height, data };
}

/** Los pixeles que no son iguales (algun canal difiere en mas de `tolerance`), en las columnas
 *  [from, to) de los dos recortes (del mismo tamano). */
export function differingPixels(
  a: Bitmap,
  b: Bitmap,
  options: { from?: number; to?: number; tolerance?: number; shift?: number } = {}
): number {
  if (a.width !== b.width || a.height !== b.height) throw new Error(`tamanos distintos: ${a.width}x${a.height} y ${b.width}x${b.height}`);
  const from = options.from ?? 0,
    to = options.to ?? a.width,
    tolerance = options.tolerance ?? 24,
    // `shift`: la columna x de `b` se compara con la x + shift de `a` (fuera de `a`, negro).
    shift = options.shift ?? 0;
  let count = 0;
  for (let y = 0; y < a.height; y += 1) {
    for (let x = from; x < to; x += 1) {
      const ax = x + shift;
      const i = (y * a.width + ax) * 4;
      const j = (y * b.width + x) * 4;
      const inside = ax >= 0 && ax < a.width;
      const ar = inside ? a.data[i]! : 0,
        ag = inside ? a.data[i + 1]! : 0,
        ab = inside ? a.data[i + 2]! : 0;
      if (Math.abs(ar - b.data[j]!) > tolerance || Math.abs(ag - b.data[j + 1]!) > tolerance || Math.abs(ab - b.data[j + 2]!) > tolerance) count += 1;
    }
  }
  return count;
}

/** Las columnas con algo pintado (alfa) de la primera celda (76 px) de un sprite. */
export function opaqueColumns(sprite: Bitmap, cell = 76): { from: number; to: number } {
  let from = cell,
    to = -1;
  for (let y = 0; y < sprite.height; y += 1)
    for (let x = 0; x < cell; x += 1)
      if (sprite.data[(y * sprite.width + x) * 4 + 3]! > 0) {
        from = Math.min(from, x);
        to = Math.max(to, x);
      }
  return { from, to };
}
