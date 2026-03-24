"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { PIPELINE_STATS } from "./constants";
import { Container } from "./primitives";

// ─── Microcopy labels ────────────────────────────────
const MICRO_LABELS = [
  "Updated weekly",
  "Partner-level targeting",
  "Verified where possible",
  "Continuously refined",
] as const;

// ─── Count-up hook ───────────────────────────────────
function useCountUp(target: number, duration = 1400) {
  const [count, setCount] = useState(0);
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!started) return;
    const start = performance.now();
    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      // cubic ease-out
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, [started, target, duration]);

  return { count, ref, started };
}

// ─── Single metric block ─────────────────────────────
function MetricBlock({
  value,
  label,
  micro,
  index,
}: {
  value: string;
  label: string;
  micro: string;
  index: number;
}) {
  const numericMatch = value.match(/^([\d,]+)/);
  const numericValue = numericMatch
    ? parseInt(numericMatch[1].replace(/,/g, ""), 10)
    : null;
  const suffix = numericMatch ? value.slice(numericMatch[1].length) : "";

  const duration = 1200 + index * 100;
  const { count, ref, started } = useCountUp(numericValue ?? 0, duration);

  return (
    <motion.div
      ref={ref}
      className="flex-1 min-w-0 text-center py-6 px-3 relative z-10"
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{
        duration: 0.5,
        delay: index * 0.1,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      {/* Animated number */}
      <span className="block text-3xl md:text-4xl font-[700] text-[#C79B2C] tabular-nums leading-none">
        {numericValue !== null
          ? `${started ? count.toLocaleString() : "0"}${suffix}`
          : value}
      </span>

      {/* Primary label */}
      <span className="block mt-2 text-xs font-medium text-[#F8F4EC]/70 tracking-wide">
        {label}
      </span>

      {/* Micro label */}
      <span className="block mt-1 text-[10px] text-[#F8F4EC]/35 uppercase tracking-widest">
        {micro}
      </span>
    </motion.div>
  );
}

// ─── Background linework (horizontal line + dots) ────
function BackgroundLine({ count }: { count: number }) {
  return (
    <motion.div
      className="absolute inset-0 flex items-center pointer-events-none"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 1.2, ease: "easeOut" }}
    >
      <div className="w-full relative h-px">
        {/* Horizontal line */}
        <motion.div
          className="absolute inset-y-0 left-0 right-0 bg-gradient-to-r from-transparent via-[#C79B2C]/15 to-transparent"
          style={{ height: 1 }}
          initial={{ scaleX: 0, transformOrigin: "left" }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
        />

        {/* Node dots at each metric position */}
        {Array.from({ length: count }).map((_, i) => {
          const position = ((i + 0.5) / count) * 100;
          return (
            <motion.div
              key={i}
              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-[#C79B2C]/25"
              style={{ left: `${position}%` }}
              initial={{ scale: 0, opacity: 0 }}
              whileInView={{ scale: 1, opacity: 1 }}
              viewport={{ once: true }}
              transition={{
                duration: 0.4,
                delay: 0.4 + i * 0.1,
                ease: "easeOut",
              }}
            />
          );
        })}
      </div>
    </motion.div>
  );
}

// ─── Vertical divider ────────────────────────────────
function Divider() {
  return (
    <div className="hidden md:flex items-center self-stretch py-4">
      <div className="w-px h-full bg-[#2E2A24]" />
    </div>
  );
}

// ─── Main export ─────────────────────────────────────
export function StatsStrip() {
  return (
    <div className="bg-[#15110E] border-y border-[#2E2A24]">
      <Container>
        <div className="relative max-w-4xl mx-auto">
          <BackgroundLine count={PIPELINE_STATS.length} />

          <div className="relative z-10 flex flex-col md:flex-row items-stretch">
            {PIPELINE_STATS.map((stat, i) => (
              <div key={stat.label} className="contents">
                {i > 0 && <Divider />}
                <MetricBlock
                  value={stat.value}
                  label={stat.label}
                  micro={MICRO_LABELS[i]}
                  index={i}
                />
              </div>
            ))}
          </div>
        </div>
      </Container>
    </div>
  );
}
