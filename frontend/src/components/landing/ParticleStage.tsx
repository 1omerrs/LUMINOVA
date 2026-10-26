import type { MotionValue } from "framer-motion";
import { useEffect, useRef, type RefObject } from "react";
import { storyModules } from "../../content/story.ts";
import {
  createBuffers,
  createLayout,
  createParticles,
  createSprite,
  createTargets,
  drawFrame,
  ease,
  months,
  resolveFrame,
  stops,
  thresholdY,
  type Layout,
} from "./particles.ts";

const particleCount = 2000;
const tag = "pointer-events-none absolute left-0 top-0 select-none whitespace-nowrap will-change-transform";

const [labelStart, labelEnd] = [stops[3][1], stops[4][1]];

export function ParticleStage({ section, progress }: { section: RefObject<HTMLElement | null>; progress: MotionValue<number> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labels = useRef<(HTMLSpanElement | null)[]>([]);
  const monthRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const sampleRef = useRef<HTMLDivElement>(null);
  const barsCaption = useRef<HTMLParagraphElement>(null);
  const stockCaption = useRef<HTMLParagraphElement>(null);
  const calloutRef = useRef<HTMLDivElement>(null);
  const limitRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = section.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !host || !ctx) {
      return;
    }

    const particles = createParticles(particleCount);
    const buffers = createBuffers(particleCount);
    const sprite = createSprite();
    let layout: Layout = createLayout(1, 1);
    let targets = createTargets(particles, layout);
    let top = 0;
    let height = 1;
    let distance = 1;
    let smooth = progress.get();
    let last = performance.now();
    let frameId = 0;
    const shown = new Map<HTMLElement, number>();

    const fade = (element: HTMLElement | null, value: number) => {
      if (!element) {
        return;
      }
      const next = Math.round(Math.min(1, Math.max(0, value)) * 1000) / 1000;
      if (shown.get(element) !== next) {
        shown.set(element, next);
        element.style.opacity = String(next);
      }
    };

    const moveTo = (element: HTMLElement | null, x: number, y: number, shift: string) => {
      if (element) {
        element.style.transform = `translate3d(${x}px, ${y}px, 0) ${shift}`;
      }
    };

    const measure = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width * ratio);
      canvas.height = Math.round(rect.height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      layout = createLayout(rect.width, rect.height);
      targets = createTargets(particles, layout);
      top = host.getBoundingClientRect().top + window.scrollY;
      height = host.offsetHeight;
      distance = Math.max(height - window.innerHeight, 1);

      const { chart } = layout;
      moveTo(sampleRef.current, chart.x, chart.y - (layout.wide ? 58 : 52), "");
      moveTo(calloutRef.current, chart.x + chart.w, chart.y, "translateX(-100%)");
      moveTo(limitRef.current, chart.x, thresholdY(layout) - 6, "translateY(-100%)");
      monthRefs.current.forEach((element, index) => {
        moveTo(element, chart.x + (chart.w * index) / (months.length - 1), chart.y + chart.h + 14, "translateX(-50%)");
      });
    };

    const tick = (now: number) => {
      frameId = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const target = Math.min(1, Math.max(0, (window.scrollY - top) / distance));
      smooth += (target - smooth) * (1 - Math.exp(-dt * 7));
      if (Math.abs(target - smooth) < 0.0002) {
        smooth = target;
      }
      if (progress.get() !== smooth) {
        progress.set(smooth);
      }
      if (window.scrollY > top + height) {
        return;
      }

      const frame = resolveFrame(smooth);
      drawFrame(ctx, particles, layout, targets, buffers, sprite, frame, smooth, now / 1000);

      const [, cluster, board, signal] = frame.weights;
      const travel = ease(Math.min(1, Math.max(0, (smooth - labelStart) / (labelEnd - labelStart))));
      labels.current.forEach((element, index) => {
        const c = layout.clusters[index];
        const fromX = c.x;
        const fromY = c.y + layout.clusterRadius * 1.35 + 8;
        const toX = layout.chart.x + layout.slot * (index + 0.5);
        const toY = layout.chart.y + layout.chart.h + 14 + (!layout.wide && index % 2 === 1 ? 14 : 0);
        moveTo(element, fromX + (toX - fromX) * travel, fromY + (toY - fromY) * travel, "translateX(-50%)");
        fade(element, (cluster + board) * (1 - Math.sin(Math.PI * travel)));
      });
      fade(sampleRef.current, board + signal);
      fade(barsCaption.current, board);
      fade(stockCaption.current, signal);
      fade(calloutRef.current, signal);
      fade(limitRef.current, signal);
      monthRefs.current.forEach((element) => fade(element, signal));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    observer.observe(host);
    void document.fonts?.load('700 64px "Plus Jakarta Sans"').then(() => {
      targets = createTargets(particles, layout);
    });
    frameId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [progress, section]);

  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_32%,rgba(124,92,252,0.2),transparent_55%)] lg:bg-[radial-gradient(ellipse_at_71%_50%,rgba(124,92,252,0.2),transparent_48%)]" />
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "96px 96px",
          maskImage: "radial-gradient(ellipse at 60% 45%, black, transparent 75%)",
        }}
      />
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      {storyModules.map((label, index) => (
        <span
          key={label}
          ref={(element) => {
            labels.current[index] = element;
          }}
          className={`${tag} font-display text-[9px] font-semibold tracking-[0.16em] text-white/80 opacity-0 lg:text-[10px]`}
        >
          {label.toLocaleUpperCase("tr")}
        </span>
      ))}

      <div ref={sampleRef} className={`${tag} opacity-0`}>
        <p className="font-display text-[10px] font-semibold tracking-[0.2em] text-[#A78BFA]">
          ÖRNEK GÖRÜNÜM <span className="text-white/45">· Canlı kayıt değildir</span>
        </p>
        <div className="relative mt-1.5 h-5">
          <p ref={barsCaption} className="absolute inset-0 text-[13px] font-medium text-white opacity-0">
            Modüllere göre açık işler
          </p>
          <p ref={stockCaption} className="absolute inset-0 text-[13px] font-medium text-white opacity-0">
            Stok seviyesi
          </p>
        </div>
      </div>

      <div ref={calloutRef} className={`${tag} border-l-2 border-violet bg-[#202432]/85 px-3 py-2 text-right opacity-0`}>
        <p className="font-display text-[10px] font-semibold tracking-[0.16em] text-[#A78BFA]">STOK · MAYIS</p>
        <p className="mt-0.5 text-[12px] font-medium text-white lg:text-[13px]">Minimum seviyenin altında</p>
      </div>

      <span ref={limitRef} className={`${tag} bg-[#10131C]/80 px-1.5 text-[10px] tracking-[0.12em] text-[#A78BFA] opacity-0`}>
        MİNİMUM SEVİYE
      </span>

      {months.map((month, index) => (
        <span
          key={month}
          ref={(element) => {
            monthRefs.current[index] = element;
          }}
          className={`${tag} text-[10px] text-[#A6ADBD] opacity-0 lg:text-[11px]`}
        >
          {month}
        </span>
      ))}
    </div>
  );
}