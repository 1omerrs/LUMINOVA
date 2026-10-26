import { MotionConfig, motion, useMotionValue, useMotionValueEvent, useTransform, type MotionValue } from "framer-motion";
import { useRef, useState } from "react";
import { sceneBreaks, sceneIndex, scenes, type StoryScene } from "../../content/story.ts";
import { GhostButton, PrimaryLink } from "./LandingActions.tsx";
import { ParticleStage } from "./ParticleStage.tsx";
import { scrollToTimeline } from "./particles.ts";

const edges = [0, ...sceneBreaks, 1];
const fadeSpan = 0.04;

export function ScrollStory() {
  return (
    <MotionConfig reducedMotion="never">
      <PinnedStory />
    </MotionConfig>
  );
}

function PinnedStory() {
  const ref = useRef<HTMLElement>(null);
  const progress = useMotionValue(0);
  const [scene, setScene] = useState(0);
  const rule = useTransform(progress, [0, 1], [0.04, 1]);

  useMotionValueEvent(progress, "change", (value) => {
    const next = sceneIndex(value);
    setScene((current) => (current === next ? current : next));
  });

  return (
    <section id="anlatim" ref={ref} className="relative h-[620vh] lg:h-[720vh]">
      <div className="sticky top-0 h-dvh overflow-hidden">
        <ParticleStage section={ref} progress={progress} />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-1/2 bg-[linear-gradient(180deg,transparent,rgba(16,19,28,0.85)_45%,#10131C)] lg:hidden" />
        <div className="relative z-20 mx-auto flex h-full max-w-6xl flex-col justify-end px-5 pb-16 pt-24 lg:justify-center lg:px-12 lg:pb-10">
          <p className="sr-only" aria-live="polite">
            {scenes[scene]?.title} {scenes[scene]?.body}
          </p>
          <div className="relative h-[250px] lg:h-[340px] lg:w-[42%]">
            {scenes.map((item, index) => (
              <SceneCopy
                key={item.id}
                item={item}
                index={index}
                progress={progress}
                active={scene === index}
                onExplore={() => scrollToTimeline(ref.current, 0.28)}
              />
            ))}
          </div>
        </div>
        <ol className="absolute bottom-5 left-5 z-20 flex gap-3 text-[11px] tracking-[0.16em] lg:bottom-8 lg:left-12">
          {scenes.map((item, index) => (
            <li key={item.id} className={index === scene ? "text-violet" : "text-white/35"}>
              {item.index}
            </li>
          ))}
        </ol>
        <motion.div aria-hidden className="absolute bottom-0 left-0 z-20 h-0.5 w-full origin-left bg-violet" style={{ scaleX: rule }} />
      </div>
    </section>
  );
}

function SceneCopy({
  item,
  index,
  progress,
  active,
  onExplore,
}: {
  item: StoryScene;
  index: number;
  progress: MotionValue<number>;
  active: boolean;
  onExplore: () => void;
}) {
  const start = edges[index];
  const end = edges[index + 1];
  const first = index === 0;
  const last = index === scenes.length - 1;
  const range = first ? [0, end - fadeSpan, end] : last ? [start, start + fadeSpan, 1] : [start, start + fadeSpan, end - fadeSpan, end];
  const opacity = useTransform(progress, range, first ? [1, 1, 0] : last ? [0, 1, 1] : [0, 1, 1, 0]);
  const y = useTransform(progress, range, first ? [0, 0, -18] : last ? [18, 0, 0] : [18, 0, 0, -18]);
  const Title = first ? "h1" : "h2";

  return (
    <motion.div style={{ opacity, y }} className="absolute inset-x-0 bottom-0 lg:inset-y-0 lg:flex lg:flex-col lg:justify-center" aria-hidden={!active} inert={active ? undefined : true}>
      <p className="font-display text-[11px] font-semibold tracking-[0.2em] text-violet">{item.index} / 05</p>
      <Title className="mt-3 max-w-xl font-display text-[1.65rem] font-semibold leading-[1.08] tracking-tight text-white sm:text-4xl lg:mt-4 lg:text-[2.65rem]">
        {item.title}
      </Title>
      <p className="mt-3 max-w-md text-[15px] leading-7 text-[#A6ADBD]">{item.body}</p>
      {first ? (
        <div className="pointer-events-auto mt-6 flex flex-wrap gap-3">
          <PrimaryLink to="/kayit">LUMINOVA’yı Keşfet</PrimaryLink>
          <GhostButton onClick={onExplore}>Nasıl Çalışır?</GhostButton>
        </div>
      ) : null}
      {last ? (
        <div className="pointer-events-auto mt-6">
          <PrimaryLink to="/kayit">LUMINOVA’yı Keşfet</PrimaryLink>
        </div>
      ) : null}
    </motion.div>
  );
}
