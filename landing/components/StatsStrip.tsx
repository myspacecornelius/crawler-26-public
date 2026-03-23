"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { PIPELINE_STATS } from "./constants";
import { Container } from "./primitives";

function useCountUp(target: number, duration = 1200) {
  const [count, setCount] = useState(0);
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setStarted(true); observer.disconnect(); } },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!started) return;
    const start = performance.now();
    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setCount(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, [started, target, duration]);

  return { count, ref };
}

function StatItem({ value, label }: { value: string; label: string }) {
  // Parse numeric portion for animation
  const numericMatch = value.match(/^([\d,]+)/);
  const numericValue = numericMatch ? parseInt(numericMatch[1].replace(/,/g, ""), 10) : null;
  const suffix = numericMatch ? value.slice(numericMatch[1].length) : "";
  const { count, ref } = useCountUp(numericValue ?? 0);

  if (numericValue !== null) {
    return (
      <div ref={ref} className="flex items-center gap-3">
        <span className="text-2xl md:text-3xl font-[700] text-honey-500 tabular-nums">
          {count.toLocaleString()}{suffix}
        </span>
        <span className="text-xs text-charcoal-text/50 uppercase tracking-wider leading-tight">{label}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-2xl md:text-3xl font-[700] text-honey-500">{value}</span>
      <span className="text-xs text-charcoal-text/50 uppercase tracking-wider leading-tight">{label}</span>
    </div>
  );
}

export function StatsStrip() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
      className="bg-charcoal-900 border-y border-charcoal-border py-6"
    >
      <Container>
        <div className="flex flex-wrap items-center justify-center gap-8 md:gap-14">
          {PIPELINE_STATS.map((s) => (
            <StatItem key={s.label} value={s.value} label={s.label} />
          ))}
        </div>
      </Container>
    </motion.div>
  );
}
