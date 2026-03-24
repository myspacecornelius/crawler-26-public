"use client";

import { motion } from "framer-motion";
import { PAIN_POINTS } from "./constants";
import { Section, SectionTitle } from "./primitives";

const EASE = [0.22, 1, 0.36, 1] as const;

const rowVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.26, ease: EASE, delay: i * 0.12 },
  }),
};

const solutionVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.26, ease: EASE, delay: i * 0.12 + 0.12 },
  }),
};

export function ProblemSolutionBand() {
  return (
    <Section>
      <SectionTitle subtitle="Most founders burn weeks on untargeted outreach. Here is how we fix that.">
        Common problems, specific solutions
      </SectionTitle>

      <div
        className="rounded-[14px] border overflow-hidden"
        style={{
          backgroundColor: "#FFFDF8",
          borderColor: "#DDD1BE",
        }}
      >
        {/* Column headers */}
        <div className="grid grid-cols-1 md:grid-cols-2">
          <div
            className="px-7 py-5 md:border-r"
            style={{ borderColor: "#DDD1BE" }}
          >
            <h3
              className="text-[15px] font-semibold uppercase tracking-wide"
              style={{ color: "#C0392B" }}
            >
              The problem
            </h3>
          </div>
          <div className="px-7 py-5">
            <h3
              className="text-[15px] font-semibold uppercase tracking-wide"
              style={{ color: "#C79B2C" }}
            >
              How we fix it
            </h3>
          </div>
        </div>

        {/* Divider below header */}
        <div className="h-px" style={{ backgroundColor: "#DDD1BE" }} />

        {/* Rows */}
        {PAIN_POINTS.map((item, i) => (
          <div key={i}>
            <div className="grid grid-cols-1 md:grid-cols-2">
              {/* Pain column */}
              <motion.div
                className="px-7 py-6 md:border-r"
                style={{ borderColor: "#DDD1BE" }}
                variants={rowVariants}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-40px" }}
                custom={i}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full mb-3"
                  style={{ backgroundColor: "#C0392B", opacity: 0.5 }}
                />
                <p
                  className="text-[15px] font-medium leading-snug"
                  style={{ color: "#1E1916" }}
                >
                  {item.pain}
                </p>
              </motion.div>

              {/* Solution column */}
              <motion.div
                className="px-7 py-6"
                variants={solutionVariants}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-40px" }}
                custom={i}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full mb-3"
                  style={{ backgroundColor: "#C79B2C", opacity: 0.5 }}
                />
                <p
                  className="text-[14px] leading-relaxed"
                  style={{ color: "#5E554C" }}
                >
                  {item.solution}
                </p>
              </motion.div>
            </div>

            {/* Row divider (skip after last row) */}
            {i < PAIN_POINTS.length - 1 && (
              <div className="h-px" style={{ backgroundColor: "#DDD1BE" }} />
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
