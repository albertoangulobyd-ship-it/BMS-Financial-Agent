// @ts-nocheck
// Los orbes de particulas "pensando" de Aurora (paso 16): el dibujo, tal cual. Es el codigo del
// "Thinking Orb" de adrielzimbril (21st.dev, @adrielzimbril/components/thinking-orb) que el
// prototipo extrajo de su vista previa publica sin cambiar el dibujo ni el algoritmo; por eso
// los nombres son de una sola letra. Solo calcula puntos y lineas y los pinta en un canvas 2D
// que le da thinking-orb.tsx: no toca el DOM, no lee datos y no pide nada a la red.
//
// Por que sin comprobar tipos: tiparlo seria reescribirlo, y entonces ya no seria el dibujo
// que eligio el dueno. La frontera tiene tipos: thinking-orb.tsx importa estas cinco funciones
// con su firma (OrbRenderer), y el resto de la app no las ve.
function gd(h, E, d) {
  for (const s of E) {
    const D = s.a ?? 1,
      T = Math.min(1, Math.max(0, s.white)),
      p = Math.round((d ? 1 - T : T) * 255);
    (h.fillStyle = `rgba(${p},${p},${p},${D})`),
      h.beginPath(),
      h.arc(s.x, s.y, s.r, 0, Math.PI * 2),
      h.fill();
  }
}
function Sd(h, E, d) {
  for (const s of E) {
    const D = s.a ?? 1,
      T = Math.min(1, Math.max(0, s.white)),
      p = Math.round((d ? 1 - T : T) * 255);
    (h.strokeStyle = `rgba(${p},${p},${p},${D})`),
      (h.lineWidth = s.w),
      h.beginPath(),
      h.moveTo(s.x1, s.y1),
      h.lineTo(s.x2, s.y2),
      h.stroke();
  }
}
function Sa(h, E, d = 0.3) {
  const s = [];
  for (const D of h) (D.a ?? 1) < 0.02 || ((D.r = Math.max(d, D.r)), s.push(D));
  return (
    s.sort((D, T) => D.z - T.z),
    { dots: s, lines: E.filter((D) => (D.a ?? 1) >= 0.02) }
  );
}
function bd(h, E, d) {
  E.lines.length && Sd(h, E.lines, d), gd(h, E.dots, d);
}
function Md(h, E, d) {
  const s = Math.min(2, (typeof window < "u" && window.devicePixelRatio) || 1),
    D = Math.max(1, Math.round(E)),
    T = Math.max(1, Math.round(d)),
    p = Math.round(D * s),
    B = Math.round(T * s);
  (h.width !== p || h.height !== B) && ((h.width = p), (h.height = B));
  const A = h.getContext("2d");
  return A.setTransform(s, 0, 0, s, 0, 0), { ctx: A, w: D, h: T };
}
function Xa(h, E, d) {
  return h + (E - h) * d;
}
function Er(h) {
  return h - Math.floor(h);
}
function Ar(h) {
  return h < 0 ? 0 : h > 1 ? 1 : h;
}
function Td(h) {
  return h * h * (3 - 2 * h);
}
function El(h, E) {
  const d = Math.sin(h * 12.9898 + E * 78.233) * 43758.5453;
  return d - Math.floor(d);
}
function si(h, E) {
  const d = Math.floor(h),
    s = Math.floor(E);
  let D = h - d,
    T = E - s;
  (D = D * D * (3 - 2 * D)), (T = T * T * (3 - 2 * T));
  const p = El(d, s),
    B = El(d + 1, s),
    A = El(d, s + 1),
    b = El(d + 1, s + 1);
  return p + (B - p) * D + (A - p) * T + (p - B - A + b) * D * T;
}
function hi(h, E) {
  const d = Math.PI * (3 - Math.sqrt(5)),
    s = 1 - 2 * ((h + 0.5) / E),
    D = Math.sqrt(Math.max(0, 1 - s * s)),
    T = h * d;
  return [D * Math.cos(T), s, D * Math.sin(T)];
}
function Ed(h, E) {
  return Math.atan2(Math.sin(h - E), Math.cos(h - E));
}
function Ca(h, E, d, s, D) {
  const T = Math.sin(E),
    p = Math.cos(E),
    B = Math.sin(h),
    A = Math.cos(h);
  return (b, x, G) => {
    const N = b * A + G * B,
      K = -b * B + G * A,
      P = x * p - K * T,
      ut = x * T + K * p;
    return [d + N * D, s - P * D, ut];
  };
}
function ja(h, E) {
  return Math.pow(h / 300, E);
}
const Ad = {
    globe: {
      latRings: 17,
      lonDensity: 44,
      rBase: 0.6,
      rDepth: 1.7,
      rBoost: 1,
      inkFar: 0.62,
      inkSpan: 0.54,
      rsPow: 0.6,
      rMin: 0.3,
    },
    orbits: {
      orbitN: 12,
      ghostN: 40,
      ghostR: 0.9,
      ghostA: 0.5,
      particles: 3,
      partR: 1.2,
      partRDepth: 1.6,
      rsPow: 0.6,
      rMin: 0.3,
    },
    rubik: {
      latRings: 15,
      lonDensity: 40,
      moveCount: 14,
      rBase: 0.6,
      rDepth: 1.7,
      rActive: 0.3,
      inkFar: 0.62,
      inkSpan: 0.54,
      rsPow: 0.6,
      rMin: 0.3,
    },
    wave: {
      rings: 15,
      lonDensity: 40,
      rBase: 0.6,
      rDepth: 1.7,
      rsPow: 0.6,
      rMin: 0.3,
    },
    web: {
      nodeN: 30,
      thr: 0.72,
      signals: 5,
      nodeR: 1.4,
      nodeRDepth: 1.8,
      lineW: 0.8,
      rsPow: 0.6,
      rMin: 0.3,
    },
    braid: {
      strandN: 52,
      turns: 3,
      ghostN: 150,
      rBase: 1.2,
      rDepth: 1.8,
      rsPow: 0.6,
      rMin: 0.3,
    },
    ribbon: {
      lanes: 5,
      segs: 88,
      ghostN: 150,
      rBase: 1.1,
      rDepth: 1.7,
      rsPow: 0.6,
      rMin: 0.3,
    },
    ring: {
      lanes: 5,
      segs: 88,
      ghostN: 0,
      faceOn: 1,
      rBase: 1.1,
      rDepth: 1.7,
      rsPow: 0.6,
      rMin: 0.3,
    },
    morph: { rDot: 0.021, iconD: 1, rMin: 0.25 },
  },
  zd = {
    orbits: {
      small: { speed: 3.9, count: 0.238, size: 2.4 },
      large: { speed: 1.885, count: 1, size: 1 },
    },
    globe: {
      small: {
        speed: 2.665,
        count: 0.105,
        size: 1.75,
        extra: { scanMul: 4.335, dimBase: 0.45 },
      },
      large: {
        speed: 2.015,
        count: 0.42,
        size: 1.15,
        extra: { scanMul: 4.08, dimBase: 0.45 },
      },
    },
    rubik: {
      small: { speed: 1.95, count: 0.088, size: 1.9 },
      large: { speed: 1.82, count: 0.35, size: 1.05 },
    },
    wave: {
      small: { speed: 3.998, count: 0.105, size: 1.6 },
      large: { speed: 4.388, count: 0.341, size: 1 },
    },
    web: {
      small: { speed: 6.63, count: 0.25, size: 1.52 },
      large: { speed: 3.315, count: 1.35, size: 0.95 },
    },
    braid: {
      small: { speed: 2.75, count: 0.1125, size: 1.36 },
      large: { speed: 1.625, count: 0.5, size: 1 },
    },
    ribbon: {
      small: {
        speed: 3.12,
        count: 0.051,
        size: 1.073,
        extra: { spin: 0, bandMul: 4.94, wobMul: 1 },
      },
      large: {
        speed: 2.34,
        count: 0.25,
        size: 0.85,
        extra: { spin: 0, bandMul: 3.9, wobMul: 1 },
      },
    },
    ring: {
      small: {
        speed: 3.78,
        count: 0.028,
        size: 1.622,
        extra: { spin: 0, bandMul: 3.968, wobMul: 0.565 },
      },
      large: {
        speed: 3.24,
        count: 0.25,
        size: 0.956,
        extra: { spin: 0, bandMul: 3.627, wobMul: 0.368 },
      },
    },
    morph: {
      small: { speed: 2.08, count: 0.53, size: 1.011, extra: { spread: 1.45 } },
      large: {
        speed: 2.405,
        count: 0.702,
        size: 0.395,
        extra: { spread: 1.45 },
      },
    },
  },
  Dd = [
    ["latRings", "lonDensity"],
    ["rings", "lonDensity"],
    ["lanes", "segs"],
  ],
  Od = ["orbitN", "ghostN", "nodeN", "strandN", "signals"],
  _d = ["iconD"],
  pd = [
    "rBase",
    "rDepth",
    "rActive",
    "rDot",
    "ghostR",
    "partR",
    "partRDepth",
    "nodeR",
    "nodeRDepth",
  ];
function Rd(h, E) {
  const d = { ...h },
    s = new Set(),
    D = Math.sqrt(E);
  for (const [T, p] of Dd)
    d[T] != null &&
      d[p] != null &&
      !s.has(T) &&
      !s.has(p) &&
      ((d[T] = Math.max(2, Math.round(d[T] * D))),
      (d[p] = Math.max(2, Math.round(d[p] * D))),
      s.add(T),
      s.add(p));
  for (const T of Od)
    d[T] != null &&
      d[T] !== 0 &&
      !s.has(T) &&
      (d[T] = Math.max(1, Math.round(d[T] * E)));
  for (const T of _d) d[T] != null && (d[T] = Math.max(0.02, d[T] * E));
  return d;
}
function Ud(h, E) {
  const d = { ...h };
  for (const s of pd) d[s] != null && (d[s] = d[s] * E);
  return d;
}
function Nd(h, E) {
  const d = zd[h],
    s = Ar((E - 20) / 44),
    D = Xa(d.small.count, d.large.count, s),
    T = Xa(d.small.size, d.large.size, s);
  let p = { ...Ad[h] };
  if ((D !== 1 && (p = Rd(p, D)), T !== 1 && (p = Ud(p, T)), d.small.extra)) {
    const B = {};
    for (const A of Object.keys(d.small.extra))
      B[A] = Xa(d.small.extra[A], d.large.extra[A], s);
    p = { ...p, ...B };
  }
  return { speed: Xa(d.small.speed, d.large.speed, s), opts: p };
}
function xd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.82,
    p = Ca(E * 0.12, 0.3, s, D, 1),
    B = ja(h, d.rsPow ?? 0.6),
    A = [],
    b = d.orbitN ?? 12,
    x = d.ghostN ?? 40,
    G = d.particles ?? 3;
  for (let N = 0; N < b; N++) {
    const K = El(N, 1.7),
      P = El(N, 5.2),
      ut = El(N, 8.9),
      q = T * (0.45 + 0.52 * K),
      lt = K * 2 * Math.PI,
      W = Math.acos(2 * P - 1),
      Z = Math.sin(W) * Math.cos(lt),
      j = Math.cos(W),
      C = Math.sin(W) * Math.sin(lt);
    let L = -j,
      $ = Z;
    const F = Math.max(1e-6, Math.sqrt(L * L + $ * $));
    (L /= F), ($ /= F);
    const ot = j * 0 - C * $,
      et = C * L - Z * 0,
      mt = Z * $ - j * L,
      dt = (0.25 + 0.55 * ut) * (ut > 0.5 ? 1 : -1);
    for (let Dt = 0; Dt < x; Dt++) {
      const ct = (Dt / x) * 2 * Math.PI,
        [gt, z, H] = p(
          (L * Math.cos(ct) + ot * Math.sin(ct)) * q,
          ($ * Math.cos(ct) + et * Math.sin(ct)) * q,
          (0 * Math.cos(ct) + mt * Math.sin(ct)) * q,
        ),
        V = (H / q + 1) / 2;
      A.push({
        x: gt,
        y: z,
        z: H,
        r: (d.ghostR ?? 0.9) * B,
        white: 0.72,
        a: (d.ghostA ?? 0.5) * (0.4 + 0.6 * V),
      });
    }
    for (let Dt = 0; Dt < G; Dt++) {
      const ct = E * dt + (Dt / G) * 2 * Math.PI + P * 6,
        [gt, z, H] = p(
          (L * Math.cos(ct) + ot * Math.sin(ct)) * q,
          ($ * Math.cos(ct) + et * Math.sin(ct)) * q,
          (0 * Math.cos(ct) + mt * Math.sin(ct)) * q,
        ),
        V = (H / q + 1) / 2;
      A.push({
        x: gt,
        y: z,
        z: H,
        r: ((d.partR ?? 1.2) + (d.partRDepth ?? 1.6) * V) * B,
        white: 0.3 - 0.22 * V,
      });
    }
  }
  return Sa(A, [], d.rMin);
}
function Hd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.82,
    p = 0.4 + 0.06 * Math.sin(E * 0.35),
    B = Ca(E * 0.5, p, s, D, T),
    A = E * (0.5 + 1.2 * (d.scanMul ?? 1)),
    b = ja(h, d.rsPow ?? 0.6),
    x = d.dimBase ?? 1,
    G = [],
    N = d.latRings ?? 17,
    K = d.lonDensity ?? 44;
  for (let P = 0; P <= N; P++) {
    const ut = -Math.PI / 2 + (P / N) * Math.PI,
      q = Math.cos(ut),
      lt = Math.sin(ut),
      W = Math.max(1, Math.round(Math.abs(q) * K));
    for (let Z = 0; Z < W; Z++) {
      const j = (Z / W) * 2 * Math.PI,
        [C, L, $] = B(q * Math.cos(j), lt, q * Math.sin(j)),
        F = ($ + 1) / 2,
        ot = Ed(j + E * 0.5, A),
        et = Math.exp(-(ot * ot) / 0.18) * Math.max(0, $);
      G.push({
        x: C,
        y: L,
        z: $,
        r:
          ((d.rBase ?? 0.6) + (d.rDepth ?? 1.7) * F + (d.rBoost ?? 1) * et) * b,
        white: (d.inkFar ?? 0.62) - (d.inkSpan ?? 0.54) * F,
        a: x + (1 - x) * Math.min(1, et),
      });
    }
  }
  return Sa(G, [], d.rMin);
}
function qd(h) {
  const E = [];
  for (let d = 0; d < h; d++) {
    const s = Math.min(2, Math.floor(El(d, 2.3) * 3)),
      D = -1 + 0.5 * Math.min(3, Math.floor(El(d, 5.9) * 4)),
      T = El(d, 7.7) < 0.5 ? 1 : -1;
    E.push({ axis: s, lo: D, hi: D + 0.5, ang: (T * Math.PI) / 2 });
  }
  return E;
}
function Yd(h, E, d, s) {
  const D = 2 * E * d + s,
    T = h % D,
    p = Array(E).fill(0);
  let B = -1;
  if (T < 2 * E * d) {
    const A = Math.floor(T / d),
      b = (T - A * d) / d,
      x = 1 - Math.pow(1 - Math.min(1, b / 0.7), 3);
    if (A < E) {
      for (let G = 0; G < A; G++) p[G] = 1;
      (p[A] = x), (B = A);
    } else {
      const G = 2 * E - 1 - A;
      for (let N = 0; N < G; N++) p[N] = 1;
      (p[G] = 1 - x), (B = G);
    }
  }
  return { amount: p, active: B };
}
function Bd(h, E, d) {
  let [s, D, T] = h,
    p = !1;
  for (let B = 0; B < E.length; B++) {
    if (d.amount[B] <= 0) continue;
    const A = E[B],
      b = A.axis === 0 ? s : A.axis === 1 ? D : T;
    if (b < A.lo || b >= A.hi) continue;
    B === d.active && (p = !0);
    const x = A.ang * d.amount[B],
      G = Math.cos(x),
      N = Math.sin(x);
    if (A.axis === 0) {
      const K = D * G - T * N;
      (T = D * N + T * G), (D = K);
    } else if (A.axis === 1) {
      const K = s * G + T * N;
      (T = -s * N + T * G), (s = K);
    } else {
      const K = s * G - D * N;
      (D = s * N + D * G), (s = K);
    }
  }
  return [s, D, T, p];
}
function Gd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.82,
    p = Ca(E * 0.55, 0.35 + 0.1 * Math.sin(E * 0.9), s, D, T),
    B = ja(h, d.rsPow ?? 0.6),
    A = d.moveCount ?? 14,
    b = qd(A),
    x = Yd(E, A, 0.42, 1.2),
    G = [],
    N = d.latRings ?? 15,
    K = d.lonDensity ?? 40;
  for (let P = 0; P <= N; P++) {
    const ut = -Math.PI / 2 + (P / N) * Math.PI,
      q = Math.cos(ut),
      lt = Math.sin(ut),
      W = Math.max(1, Math.round(Math.abs(q) * K));
    for (let Z = 0; Z < W; Z++) {
      const j = (Z / W) * 2 * Math.PI,
        [C, L, $, F] = Bd([q * Math.cos(j), lt, q * Math.sin(j)], b, x),
        [ot, et, mt] = p(C, L, $),
        dt = (mt + 1) / 2;
      G.push({
        x: ot,
        y: et,
        z: mt,
        r:
          ((d.rBase ?? 0.6) +
            (d.rDepth ?? 1.7) * dt +
            (F ? (d.rActive ?? 0.3) : 0)) *
          B,
        white: (d.inkFar ?? 0.62) - (d.inkSpan ?? 0.54) * dt - (F ? 0.14 : 0),
      });
    }
  }
  return Sa(G, [], d.rMin);
}
function Xd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.874,
    p = Ca(E * 0.18, 0.38, s, D, 1),
    B = ja(h, d.rsPow ?? 0.6),
    A = [],
    b = d.rings ?? 15,
    x = d.lonDensity ?? 40;
  for (let G = 0; G <= b; G++) {
    const N = -Math.PI / 2 + (G / b) * Math.PI,
      K = Math.cos(N),
      P = Math.sin(N),
      ut =
        0.62 * Math.sin(E * 2.1 - G * 0.52) +
        0.38 * Math.sin(E * 1.27 + G * 0.83),
      q = T * (0.88 + 0.105 * ut),
      lt = Math.max(1, Math.round(Math.abs(K) * x));
    for (let W = 0; W < lt; W++) {
      const Z = (W / lt) * 2 * Math.PI,
        [j, C, L] = p(K * Math.cos(Z) * q, P * q, K * Math.sin(Z) * q),
        $ = (L / T + 1) / 2,
        F = Math.max(0, ut);
      A.push({
        x: j,
        y: C,
        z: L,
        r: ((d.rBase ?? 0.6) + (d.rDepth ?? 1.7) * $) * (1 + 0.4 * F) * B,
        white: 0.66 - 0.56 * $ - 0.1 * F,
      });
    }
  }
  return Sa(A, [], d.rMin);
}
function Cd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.8 * (d.spread ?? 1),
    p = Ca(E * 0.12, 0.32, s, D, T),
    B = ja(h, d.rsPow ?? 0.6),
    A = d.nodeN ?? 30,
    b = d.thr ?? 0.72,
    x = d.nodeR ?? 1.4,
    G = d.nodeRDepth ?? 1.8,
    N = [];
  for (let q = 0; q < A; q++) {
    const lt = hi(q, A),
      W = lt[0] + 0.3 * (si(q * 0.31 + 9, E * 0.24) - 0.5) * 2,
      Z = lt[1] + 0.3 * (si(q * 0.53 + 27, E * 0.21) - 0.5) * 2,
      j = lt[2] + 0.3 * (si(q * 0.77 + 55, E * 0.27) - 0.5) * 2,
      C = Math.sqrt(W * W + Z * Z + j * j);
    N.push([W / C, Z / C, j / C]);
  }
  const K = [],
    P = [];
  for (let q = 0; q < A; q++)
    for (let lt = q + 1; lt < A; lt++) {
      const W = N[q][0] - N[lt][0],
        Z = N[q][1] - N[lt][1],
        j = N[q][2] - N[lt][2],
        C = Math.sqrt(W * W + Z * Z + j * j);
      if (C >= b) continue;
      const [L, $, F] = p(N[q][0], N[q][1], N[q][2]),
        [ot, et, mt] = p(N[lt][0], N[lt][1], N[lt][2]),
        dt = ((F + mt) / 2 + 1) / 2;
      K.push({
        x1: L,
        y1: $,
        x2: ot,
        y2: et,
        white: 0.42,
        a: (1 - C / b) * (0.3 + 0.55 * dt),
        w: Math.max(0.6, (d.lineW ?? 0.8) * B),
      });
    }
  for (let q = 0; q < A; q++) {
    const [lt, W, Z] = p(N[q][0], N[q][1], N[q][2]),
      j = (Z + 1) / 2,
      C = 1 + 0.25 * Math.sin(E * 1.4 + q * 2.7);
    P.push({
      x: lt,
      y: W,
      z: Z,
      r: (x + G * j) * C * B,
      white: 0.55 - 0.45 * j,
    });
  }
  const ut = d.signals ?? 5;
  for (let q = 0; q < ut; q++) {
    const lt = Math.floor(E * 0.55 + q * 7.31),
      W = Math.floor(El(lt, q * 3.1 + 1.7) * A),
      Z = Math.floor(El(lt, q * 5.7 + 4.2) * A);
    if (W === Z) continue;
    const j = Er(E * 0.55 + q * 7.31),
      C = Xa(N[W][0], N[Z][0], j),
      L = Xa(N[W][1], N[Z][1], j),
      $ = Xa(N[W][2], N[Z][2], j),
      F = Math.max(1e-6, Math.sqrt(C * C + L * L + $ * $)),
      [ot, et, mt] = p(C / F, L / F, $ / F),
      dt = (mt + 1) / 2;
    P.push({
      x: ot,
      y: et,
      z: mt,
      r: (x * 1.5 + G * dt) * B,
      white: 0.05,
      a: 0.5 + 0.5 * dt,
    });
  }
  return Sa(P, K, d.rMin);
}
function jd(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.76,
    p = Ca(E * 0.4, 0.3, s, D, 1),
    B = ja(h, d.rsPow ?? 0.6),
    A = [],
    b = d.ghostN ?? 150;
  for (let N = 0; N < b; N++) {
    const K = hi(N, b),
      [P, ut, q] = p(K[0] * T, K[1] * T, K[2] * T),
      lt = (q / T + 1) / 2;
    A.push({ x: P, y: ut, z: q, r: 0.8 * B, white: 0.78, a: 0.1 + 0.22 * lt });
  }
  const x = d.strandN ?? 52,
    G = d.turns ?? 3;
  for (let N = 0; N < 3; N++) {
    const K = (N / 3) * 2 * Math.PI;
    for (let P = 0; P < x; P++) {
      const ut = (Er(P / x + E * 0.045) * 2 - 1) * 0.96,
        q = Math.sqrt(Math.max(0, 1 - ut * ut)),
        lt = Math.min(1, (1 - Math.abs(ut)) / 0.1),
        W = ut * Math.PI * G + K,
        Z = 1 + 0.075 * Math.sin(ut * Math.PI * G * 2 + K * 2 + E * 0.8),
        j = q * T * Z,
        [C, L, $] = p(Math.cos(W) * j, ut * T * Z, Math.sin(W) * j),
        F = ($ / T + 1) / 2;
      A.push({
        x: C,
        y: L,
        z: $,
        r: ((d.rBase ?? 1.2) + (d.rDepth ?? 1.8) * F) * B,
        white: 0.55 - 0.45 * F,
        a: lt * (0.45 + 0.55 * F),
      });
    }
  }
  return Sa(A, [], d.rMin);
}
function gr(h, E, d) {
  const s = h / 2,
    D = h / 2,
    T = (h / 2) * 0.78,
    p = d.spin ?? 1,
    B = Ca(E * 0.1 * p, 0.3, s, D, 1),
    A = ja(h, d.rsPow ?? 0.6),
    b = [],
    x = d.ghostN ?? 150;
  for (let et = 0; et < x; et++) {
    const mt = hi(et, x),
      [dt, Dt, ct] = B(mt[0] * T, mt[1] * T, mt[2] * T),
      gt = (ct / T + 1) / 2;
    b.push({
      x: dt,
      y: Dt,
      z: ct,
      r: 0.8 * A,
      white: 0.78,
      a: 0.1 + 0.22 * gt,
    });
  }
  const G = E * 0.24 * p,
    N = d.faceOn ? -0.3 : 0.55 + 0.3 * Math.sin(E * 0.18) * p,
    K = Math.cos(G),
    P = Math.sin(G),
    ut = -P * Math.sin(N),
    q = Math.cos(N),
    lt = K * Math.sin(N),
    W = 0 * lt - P * q,
    Z = P * ut - K * lt,
    j = K * q - 0 * ut,
    C = 0.23 * (d.wobMul ?? 1),
    L = d.faceOn ? T / (1 + 0.85 * C) : T,
    $ = d.lanes ?? 5,
    F = d.segs ?? 88,
    ot = Math.max(1, Math.round($ * (d.bandMul ?? 1)));
  for (let et = 0; et < ot; et++) {
    const mt = (et - (ot - 1) / 2) * 0.075,
      dt = Math.abs(et - (ot - 1) / 2) / Math.max(1, (ot - 1) / 2);
    for (let Dt = 0; Dt < F; Dt++) {
      const ct = (Dt / F) * 2 * Math.PI,
        gt =
          (0.16 * Math.sin(ct * 3 - E * 1.7 + et * 0.22) +
            0.07 * Math.sin(ct * 5 + E * 1.1)) *
          (d.wobMul ?? 1),
        z = d.faceOn ? 1 + gt : 1,
        H = d.faceOn ? mt : mt + gt,
        V = K * Math.cos(ct) + ut * Math.sin(ct) + W * H,
        yt = 0 * Math.cos(ct) + q * Math.sin(ct) + Z * H,
        r = P * Math.cos(ct) + lt * Math.sin(ct) + j * H,
        U = Math.sqrt(V * V + yt * yt + r * r),
        X = L * z,
        [Y, J, ft] = B((V / U) * X, (yt / U) * X, (r / U) * X),
        k = (ft / T + 1) / 2;
      b.push({
        x: Y,
        y: J,
        z: ft,
        r: ((d.rBase ?? 1.1) + (d.rDepth ?? 1.7) * k) * (1 - 0.25 * dt) * A,
        white: 0.52 - 0.44 * k + 0.18 * dt,
        a: 0.4 + 0.6 * k,
      });
    }
  }
  return Sa(b, [], d.rMin);
}
const Qd = [
    [],
    [
      [0, -0.26],
      [0.24, 0.16],
      [-0.24, 0.16],
    ],
    [
      [0, -0.2],
      [0.2, -0.2],
      [0.2, 0.2],
      [-0.2, 0.2],
      [-0.2, -0.2],
    ],
  ],
  Ga = 160,
  Sr = 1.4,
  Zd = 0.9;
function Ld(h, E) {
  const d = h.length,
    s = [];
  let D = 0;
  for (let p = 0; p < d; p++) {
    const B = h[p],
      A = h[(p + 1) % d],
      b = Math.hypot(A[0] - B[0], A[1] - B[1]);
    s.push(b), (D += b);
  }
  const T = [];
  for (let p = 0; p < E; p++) {
    let B = (p / E) * D,
      A = 0;
    for (; B > s[A] && A < d - 1; ) (B -= s[A]), A++;
    const b = h[A],
      x = h[(A + 1) % d],
      G = s[A] ? Math.min(1, B / s[A]) : 0;
    T.push([b[0] + (x[0] - b[0]) * G, b[1] + (x[1] - b[1]) * G]);
  }
  return T;
}
function br(h, E) {
  const d = Qd[h];
  if (!d || d.length === 0) {
    const s = [];
    for (let D = 0; D < E; D++) {
      const T = -Math.PI / 2 + (D / E) * 2 * Math.PI;
      s.push([Math.cos(T) * 0.24, Math.sin(T) * 0.24]);
    }
    return s;
  }
  return Ld(d, E);
}
function Vd(h, E, d) {
  const T = E % 6.8999999999999995,
    p = Math.floor(T / 2.3),
    B = T - p * 2.3,
    A = B > Sr ? Td((B - Sr) / Zd) : 0,
    b = d.spread ?? 1,
    x = br(p, Ga),
    G = br((p + 1) % 3, Ga),
    N = [];
  for (let L = 0; L < Ga; L++)
    N.push([
      (x[L][0] + (G[L][0] - x[L][0]) * A) * b,
      (x[L][1] + (G[L][1] - x[L][1]) * A) * b,
    ]);
  const K = [];
  let P = 0;
  for (let L = 0; L < Ga; L++) {
    const $ = N[L],
      F = N[(L + 1) % Ga],
      ot = Math.hypot(F[0] - $[0], F[1] - $[1]);
    K.push(ot), (P += ot);
  }
  const ut = Math.max(6, Math.round(34 * (d.iconD ?? 1))),
    q = (d.rDot ?? 0.021) * 1.35 * b,
    lt = 1 + 0.02 * Math.sin(B * 3.1),
    W = h / 2,
    Z = [];
  let j = 0,
    C = 0;
  for (let L = 0; L < ut; L++) {
    const $ = (L / ut) * P;
    for (; C + K[j] < $ && j < Ga - 1; ) (C += K[j]), j++;
    const F = N[j],
      ot = N[(j + 1) % Ga],
      et = K[j] ? Math.min(1, ($ - C) / K[j]) : 0,
      mt = (F[0] + (ot[0] - F[0]) * et) * lt,
      dt = (F[1] + (ot[1] - F[1]) * et) * lt;
    Z.push({
      x: W + mt * h,
      y: W + dt * h,
      z: 0,
      r: Math.max(0.35, q * h),
      white: 0.1,
    });
  }
  return Sa(Z, [], d.rMin);
}
const Kd = {
  orbits: xd,
  globe: Hd,
  rubik: Gd,
  wave: Xd,
  web: Cd,
  braid: jd,
  ribbon: gr,
  ring: gr,
  morph: Vd,
};

export {
  Md as setupCanvasDpr,
  Ar as clamp,
  Nd as presetFor,
  Kd as renderers,
  bd as renderOrbScene,
};
