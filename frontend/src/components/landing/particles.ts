const TAU = Math.PI * 2;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export type StateId = 0 | 1 | 2 | 3 | 4;

export const stops: readonly (readonly [StateId, number])[] = [
  [0, 0],
  [0, 0.07],
  [1, 0.23],
  [1, 0.33],
  [2, 0.47],
  [2, 0.55],
  [3, 0.69],
  [3, 0.77],
  [4, 0.91],
  [4, 1],
];

export const moduleCount = 8;
export const months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz"];

const barHeights = [0.62, 0.46, 0.78, 0.54, 0.86, 0.38, 0.68, 0.5];
const series = [0.64, 0.72, 0.6, 0.76, 0.28, 0.5];
const dipAt = 0.8;
export const threshold = 0.42;

const palette = ["#A78BFA", "#7C5CFC", "#F6F7FB"];

export type Box = { x: number; y: number; w: number; h: number };

export type Layout = {
  width: number;
  height: number;
  wide: boolean;
  region: Box;
  center: { x: number; y: number };
  radius: number;
  clusters: { x: number; y: number }[];
  clusterRadius: number;
  chart: Box;
  slot: number;
  barWidth: number;
  dot: number;
};

export type Particles = {
  count: number;
  module: Uint8Array;
  group: Uint8Array;
  seeds: Float32Array;
  u: Float32Array;
  sphere: Float32Array;
  local: Float32Array;
  ring: Uint8Array;
  orbit: Uint8Array;
  groups: number[][];
};

export type Targets = {
  bars: Float32Array;
  barAlpha: Float32Array;
  line: Float32Array;
  lineAlpha: Float32Array;
  word: Float32Array;
};

export type Frame = {
  from: StateId;
  to: StateId;
  mix: number;
  weights: number[];
};

function clamp01(value: number) {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

export function ease(value: number) {
  return value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function random(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createParticles(count: number): Particles {
  const next = random(2026);
  const module = new Uint8Array(count);
  const group = new Uint8Array(count);
  const seeds = new Float32Array(count * 6);
  const u = new Float32Array(count);
  const sphere = new Float32Array(count * 3);
  const local = new Float32Array(count * 3);
  const ring = new Uint8Array(count);
  const orbit = new Uint8Array(count);
  const groups: number[][] = [[], [], []];
  const perModule = Math.ceil(count / moduleCount);

  for (let i = 0; i < count; i += 1) {
    const m = i % moduleCount;
    module[i] = m;
    for (let k = 0; k < 6; k += 1) {
      seeds[i * 6 + k] = next();
    }
    u[i] = (m + seeds[i * 6]) / moduleCount;

    const y = 1 - (2 * (i + 0.5)) / count;
    const r = Math.sqrt(1 - y * y);
    sphere[i * 3] = Math.cos(i * GOLDEN) * r;
    sphere[i * 3 + 1] = y;
    sphere[i * 3 + 2] = Math.sin(i * GOLDEN) * r;

    const j = Math.floor(i / moduleCount);
    const ly = 1 - (2 * (j + 0.5)) / perModule;
    const lr = Math.sqrt(1 - ly * ly);
    local[i * 3] = Math.cos(j * GOLDEN) * lr;
    local[i * 3 + 1] = ly;
    local[i * 3 + 2] = Math.sin(j * GOLDEN) * lr;

    const pick = seeds[i * 6 + 3];
    ring[i] = pick < 0.2 ? 1 : 0;
    orbit[i] = pick < 0.14 ? 1 : 0;

    const tone = seeds[i * 6 + 4];
    group[i] = tone < 0.55 ? 0 : tone < 0.86 ? 1 : 2;
    groups[group[i]].push(i);
  }

  return { count, module, group, seeds, u, sphere, local, ring, orbit, groups };
}

export function createLayout(width: number, height: number): Layout {
  const wide = width >= 1024;
  const region: Box = wide
    ? { x: width * 0.47, y: height * 0.14, w: width * 0.48, h: height * 0.74 }
    : { x: width * 0.06, y: height * 0.1, w: width * 0.88, h: height * 0.46 };
  const center = { x: region.x + region.w / 2, y: region.y + region.h / 2 };
  const radius = Math.min(region.w, region.h) * 0.33;
  const clusters = Array.from({ length: moduleCount }, (_, index) => {
    const angle = -Math.PI / 2 + (index * TAU) / moduleCount;
    return {
      x: center.x + Math.cos(angle) * region.w * 0.37,
      y: center.y + Math.sin(angle) * region.h * 0.34,
    };
  });
  const chart: Box = {
    x: region.x + region.w * 0.04,
    y: region.y + region.h * 0.16,
    w: region.w * 0.92,
    h: region.h * 0.66,
  };
  const slot = chart.w / moduleCount;

  return {
    width,
    height,
    wide,
    region,
    center,
    radius,
    clusters,
    clusterRadius: radius * 0.2,
    chart,
    slot,
    barWidth: slot * 0.5,
    dot: wide ? 1.7 : 1.35,
  };
}

export function curveY(layout: Layout, u: number) {
  const f = clamp01(u) * (series.length - 1);
  const i = Math.min(Math.floor(f), series.length - 2);
  const t = f - i;
  const p0 = series[Math.max(i - 1, 0)];
  const p1 = series[i];
  const p2 = series[i + 1];
  const p3 = series[Math.min(i + 2, series.length - 1)];
  const value =
    0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t);
  return layout.chart.y + layout.chart.h * (1 - value);
}

export function dipPoint(layout: Layout) {
  return { x: layout.chart.x + layout.chart.w * dipAt, y: curveY(layout, dipAt) };
}

export function thresholdY(layout: Layout) {
  return layout.chart.y + layout.chart.h * (1 - threshold);
}

function sampleWordmark(layout: Layout): Float32Array {
  const box = layout.region;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(box.w));
  canvas.height = Math.max(1, Math.ceil(box.h));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    return new Float32Array();
  }
  const setFont = (size: number) => {
    ctx.font = `700 ${size}px "Plus Jakarta Sans", sans-serif`;
    ctx.letterSpacing = `${size * 0.08}px`;
  };
  setFont(100);
  const measured = ctx.measureText("LUMINOVA").width;
  const size = Math.min((100 * box.w * 0.9) / measured, box.h * 0.4);
  setFont(size);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#fff";
  ctx.fillText("LUMINOVA", canvas.width / 2 + size * 0.04, canvas.height / 2);

  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  const step = Math.max(2, Math.round(size / 30));
  const points: number[] = [];
  for (let x = 0; x < canvas.width; x += step) {
    for (let y = 0; y < canvas.height; y += step) {
      if (data[(y * canvas.width + x) * 4 + 3] > 140) {
        points.push(box.x + x, box.y + y);
      }
    }
  }
  return new Float32Array(points);
}

export function createTargets(particles: Particles, layout: Layout): Targets {
  const { count, module, seeds, u, orbit } = particles;
  const bars = new Float32Array(count * 2);
  const barAlpha = new Float32Array(count);
  const line = new Float32Array(count * 2);
  const lineAlpha = new Float32Array(count);
  const word = new Float32Array(count * 2);
  const { chart, slot, barWidth } = layout;
  const baseline = chart.y + chart.h;

  for (let i = 0; i < count; i += 1) {
    const m = module[i];
    const a = seeds[i * 6 + 1];
    const b = seeds[i * 6 + 2];
    const lift = Math.pow(b, 0.75);
    bars[i * 2] = chart.x + slot * (m + 0.5) + (a - 0.5) * barWidth;
    bars[i * 2 + 1] = baseline - lift * barHeights[m] * chart.h;
    barAlpha[i] = 0.3 + 0.7 * lift;

    const x = chart.x + chart.w * u[i];
    const top = curveY(layout, u[i]);
    if (seeds[i * 6 + 5] < 0.56) {
      line[i * 2] = x;
      line[i * 2 + 1] = top + (a - 0.5) * 3;
      lineAlpha[i] = 1;
    } else {
      const depth = Math.pow(b, 1.7);
      line[i * 2] = x;
      line[i * 2 + 1] = top + (baseline - top) * depth;
      lineAlpha[i] = 0.42 * (1 - depth) + 0.06;
    }
  }

  const points = sampleWordmark(layout);
  const total = points.length / 2;
  const order = Array.from({ length: count }, (_, index) => index)
    .filter((index) => orbit[index] === 0)
    .sort((left, right) => u[left] - u[right]);
  const columns = Array.from({ length: total }, (_, index) => index).sort((left, right) => points[left * 2] - points[right * 2]);

  order.forEach((index, rank) => {
    if (total === 0) {
      word[index * 2] = layout.center.x;
      word[index * 2 + 1] = layout.center.y;
      return;
    }
    const point = columns[Math.min(total - 1, Math.floor((rank * total) / order.length))];
    word[index * 2] = points[point * 2] + (seeds[index * 6 + 1] - 0.5) * 1.2;
    word[index * 2 + 1] = points[point * 2 + 1] + (seeds[index * 6 + 2] - 0.5) * 1.2;
  });

  return { bars, barAlpha, line, lineAlpha, word };
}

export function resolveFrame(progress: number): Frame {
  const weights = [0, 0, 0, 0, 0];
  for (let k = 0; k < stops.length - 1; k += 1) {
    const [from, start] = stops[k];
    const [to, end] = stops[k + 1];
    if (progress <= end || k === stops.length - 2) {
      const mix = from === to ? 0 : clamp01((progress - start) / (end - start));
      weights[from] += 1 - mix;
      weights[to] += mix;
      return { from, to, mix, weights };
    }
  }
  weights[4] = 1;
  return { from: 4, to: 4, mix: 0, weights };
}

const scratch = new Float32Array(4);

function place(state: StateId, i: number, particles: Particles, layout: Layout, targets: Targets, time: number, progress: number) {
  const { seeds } = particles;
  const out = scratch;

  if (state === 0) {
    const r = layout.radius;
    let x: number;
    let y: number;
    let z: number;
    if (particles.ring[i]) {
      const angle = seeds[i * 6] * TAU + time * 0.22;
      const reach = r * (1.36 + seeds[i * 6 + 1] * 0.06);
      const px = Math.cos(angle) * reach;
      const py = (seeds[i * 6 + 2] - 0.5) * r * 0.04;
      const pz = Math.sin(angle) * reach;
      const tilt = 1.2;
      const ty = py * Math.cos(tilt) - pz * Math.sin(tilt);
      z = py * Math.sin(tilt) + pz * Math.cos(tilt);
      const roll = -0.3;
      x = px * Math.cos(roll) - ty * Math.sin(roll);
      y = px * Math.sin(roll) + ty * Math.cos(roll);
    } else {
      const spin = time * 0.16 + progress * 2.4;
      const sx = particles.sphere[i * 3] * r;
      const sy = particles.sphere[i * 3 + 1] * r;
      const sz = particles.sphere[i * 3 + 2] * r;
      const rx = sx * Math.cos(spin) + sz * Math.sin(spin);
      const rz = -sx * Math.sin(spin) + sz * Math.cos(spin);
      const tilt = 0.38;
      x = rx;
      y = sy * Math.cos(tilt) - rz * Math.sin(tilt);
      z = sy * Math.sin(tilt) + rz * Math.cos(tilt);
    }
    const focal = r * 4;
    const scale = focal / (focal + z);
    out[0] = layout.center.x + x * scale;
    out[1] = layout.center.y + y * scale;
    out[2] = layout.dot * scale;
    out[3] = 0.22 + 0.78 * clamp01(0.5 - z / (r * 2.4));
    return out;
  }

  if (state === 1) {
    const m = particles.module[i];
    const c = layout.clusters[m];
    const r = layout.clusterRadius * (1 + 0.05 * Math.sin(time * 1.4 + m));
    const spin = time * 0.5 + m * 0.8;
    const lx = particles.local[i * 3] * r;
    const ly = particles.local[i * 3 + 1] * r;
    const lz = particles.local[i * 3 + 2] * r;
    const rx = lx * Math.cos(spin) + lz * Math.sin(spin);
    const rz = -lx * Math.sin(spin) + lz * Math.cos(spin);
    const focal = r * 5;
    const scale = focal / (focal + rz);
    out[0] = c.x + rx * scale;
    out[1] = c.y + (ly * Math.cos(0.4) - rz * Math.sin(0.4)) * scale;
    out[2] = layout.dot * scale;
    out[3] = 0.3 + 0.7 * clamp01(0.5 - rz / (r * 2.2));
    return out;
  }

  if (state === 2) {
    out[0] = targets.bars[i * 2];
    out[1] = targets.bars[i * 2 + 1];
    out[2] = layout.dot;
    out[3] = targets.barAlpha[i];
    return out;
  }

  if (state === 3) {
    const flow = 0.78 + 0.22 * Math.sin(time * 2.6 - particles.u[i] * 14);
    out[0] = targets.line[i * 2];
    out[1] = targets.line[i * 2 + 1];
    out[2] = layout.dot;
    out[3] = targets.lineAlpha[i] * flow;
    return out;
  }

  if (particles.orbit[i]) {
    const angle = seeds[i * 6] * TAU + time * 0.18;
    const depth = Math.sin(angle);
    const roll = -0.1;
    const ox = Math.cos(angle) * layout.region.w * 0.5;
    const oy = depth * layout.region.h * 0.17;
    out[0] = layout.center.x + ox * Math.cos(roll) - oy * Math.sin(roll);
    out[1] = layout.center.y + ox * Math.sin(roll) + oy * Math.cos(roll);
    out[2] = layout.dot * (0.8 + 0.4 * (depth * 0.5 + 0.5));
    out[3] = 0.25 + 0.6 * (depth * 0.5 + 0.5);
    return out;
  }

  out[0] = targets.word[i * 2];
  out[1] = targets.word[i * 2 + 1];
  out[2] = layout.dot * 1.15;
  out[3] = 0.82 + 0.18 * Math.sin(time * 2 + seeds[i * 6 + 5] * 12);
  return out;
}

export function scrollToTimeline(section: HTMLElement | null, portion: number) {
  if (!section) {
    return;
  }
  const top = section.getBoundingClientRect().top + window.scrollY;
  window.scrollTo({ top: top + (section.offsetHeight - window.innerHeight) * portion, behavior: "auto" });
}

export function createSprite() {
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const glow = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    glow.addColorStop(0, "rgba(246,247,251,0.9)");
    glow.addColorStop(0.25, "rgba(167,139,250,0.45)");
    glow.addColorStop(1, "rgba(124,92,252,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, 32, 32);
  }
  return canvas;
}

export type Buffers = { x: Float32Array; y: Float32Array; size: Float32Array; alpha: Float32Array };

export function createBuffers(count: number): Buffers {
  return {
    x: new Float32Array(count),
    y: new Float32Array(count),
    size: new Float32Array(count),
    alpha: new Float32Array(count),
  };
}

export function drawFrame(
  ctx: CanvasRenderingContext2D,
  particles: Particles,
  layout: Layout,
  targets: Targets,
  buffers: Buffers,
  sprite: HTMLCanvasElement,
  frame: Frame,
  progress: number,
  time: number,
) {
  const { from, to, mix, weights } = frame;
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, layout.width, layout.height);
  drawGuides(ctx, layout, weights, time);

  for (let i = 0; i < particles.count; i += 1) {
    const a = place(from, i, particles, layout, targets, time, progress);
    const ax = a[0];
    const ay = a[1];
    const as = a[2];
    const aa = a[3];
    if (from === to) {
      buffers.x[i] = ax;
      buffers.y[i] = ay;
      buffers.size[i] = as;
      buffers.alpha[i] = aa;
      continue;
    }
    const b = place(to, i, particles, layout, targets, time, progress);
    const delay = particles.seeds[i * 6 + 5] * 0.5 + particles.u[i] * 0.5;
    const t = ease(clamp01((mix - delay * 0.4) / 0.6));
    const dx = b[0] - ax;
    const dy = b[1] - ay;
    const length = Math.hypot(dx, dy) || 1;
    const arc = (particles.seeds[i * 6 + 2] - 0.5) * Math.min(length * 0.6, 160) * Math.sin(Math.PI * t);
    buffers.x[i] = ax + dx * t - (dy / length) * arc;
    buffers.y[i] = ay + dy * t + (dx / length) * arc;
    buffers.size[i] = (as + (b[2] - as) * t) * (1 + 0.6 * Math.sin(Math.PI * t));
    buffers.alpha[i] = aa + (b[3] - aa) * t;
  }

  ctx.globalCompositeOperation = "lighter";
  for (let g = 0; g < 3; g += 1) {
    ctx.fillStyle = palette[g];
    for (const i of particles.groups[g]) {
      const size = buffers.size[i];
      ctx.globalAlpha = buffers.alpha[i];
      ctx.fillRect(buffers.x[i] - size / 2, buffers.y[i] - size / 2, size, size);
    }
  }
  for (const i of particles.groups[2]) {
    const glow = buffers.size[i] * 7;
    ctx.globalAlpha = buffers.alpha[i] * 0.55;
    ctx.drawImage(sprite, buffers.x[i] - glow / 2, buffers.y[i] - glow / 2, glow, glow);
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
}

function drawGuides(ctx: CanvasRenderingContext2D, layout: Layout, weights: number[], time: number) {
  const { chart, center, clusters } = layout;
  const hub = weights[1];
  if (hub > 0.01) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(167,139,250,${0.2 * hub})`;
    ctx.beginPath();
    for (const c of clusters) {
      ctx.moveTo(center.x, center.y);
      ctx.lineTo(c.x, c.y);
    }
    ctx.stroke();
    ctx.strokeStyle = `rgba(167,139,250,${0.12 * hub})`;
    ctx.beginPath();
    ctx.ellipse(center.x, center.y, layout.region.w * 0.37, layout.region.h * 0.34, 0, 0, TAU);
    ctx.stroke();
    ctx.fillStyle = `rgba(124,92,252,${0.9 * hub})`;
    ctx.beginPath();
    ctx.arc(center.x, center.y, 3.5, 0, TAU);
    ctx.fill();
  }

  const board = Math.min(1, weights[2] + weights[3]);
  if (board > 0.01) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(246,247,251,${0.07 * board})`;
    ctx.beginPath();
    for (const k of [0, 1 / 3, 2 / 3]) {
      const y = Math.round(chart.y + chart.h * k) + 0.5;
      ctx.moveTo(chart.x, y);
      ctx.lineTo(chart.x + chart.w, y);
    }
    ctx.stroke();
    ctx.strokeStyle = `rgba(246,247,251,${0.24 * board})`;
    ctx.beginPath();
    const base = Math.round(chart.y + chart.h) + 0.5;
    ctx.moveTo(chart.x, base);
    ctx.lineTo(chart.x + chart.w, base);
    ctx.stroke();
  }

  const signal = weights[3];
  if (signal > 0.01) {
    const base = chart.y + chart.h;
    const fill = ctx.createLinearGradient(0, chart.y, 0, base);
    fill.addColorStop(0, `rgba(124,92,252,${0.28 * signal})`);
    fill.addColorStop(1, "rgba(124,92,252,0)");
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.moveTo(chart.x, base);
    for (let step = 0; step <= 60; step += 1) {
      const u = step / 60;
      ctx.lineTo(chart.x + chart.w * u, curveY(layout, u));
    }
    ctx.lineTo(chart.x + chart.w, base);
    ctx.closePath();
    ctx.fill();

    const limit = Math.round(thresholdY(layout)) + 0.5;
    ctx.setLineDash([5, 7]);
    ctx.strokeStyle = `rgba(167,139,250,${0.6 * signal})`;
    ctx.beginPath();
    ctx.moveTo(chart.x, limit);
    ctx.lineTo(chart.x + chart.w, limit);
    ctx.stroke();
    ctx.setLineDash([]);

    const dip = dipPoint(layout);
    ctx.strokeStyle = `rgba(167,139,250,${0.45 * signal})`;
    ctx.beginPath();
    ctx.moveTo(dip.x + 0.5, chart.y + (layout.wide ? 64 : 58));
    ctx.lineTo(dip.x + 0.5, dip.y - 12);
    ctx.stroke();

    const pulse = (time * 0.7) % 1;
    ctx.strokeStyle = `rgba(167,139,250,${(1 - pulse) * 0.8 * signal})`;
    ctx.beginPath();
    ctx.arc(dip.x, dip.y, 8 + pulse * 24, 0, TAU);
    ctx.stroke();
    ctx.strokeStyle = `rgba(246,247,251,${0.9 * signal})`;
    ctx.beginPath();
    ctx.arc(dip.x, dip.y, 6, 0, TAU);
    ctx.stroke();
  }
}
