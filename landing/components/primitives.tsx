"use client";

import { useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Info, User } from "lucide-react";

// ═══════════════════════════════════════════════════
//  PRIMITIVES — updated design system
// ═══════════════════════════════════════════════════

export function Container({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`max-w-container mx-auto px-6 ${className}`}>{children}</div>;
}

export function Section({ children, id, className = "" }: { children: ReactNode; id?: string; className?: string }) {
  return (
    <motion.section
      id={id}
      className={`py-24 ${className}`}
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <Container>{children}</Container>
    </motion.section>
  );
}

export function SectionTitle({ children, subtitle }: { children: ReactNode; subtitle?: string }) {
  return (
    <div className="mb-12 md:mb-16 max-w-prose">
      <h2 className="text-[30px] md:text-[36px] leading-[1.15] font-[650] text-text-primary tracking-tight">{children}</h2>
      {subtitle && <p className="mt-3 text-[16px] leading-relaxed text-text-secondary max-w-xl">{subtitle}</p>}
    </div>
  );
}

export function UnderlineAccent({ children }: { children: ReactNode }) {
  return (
    <span className="relative inline-block">
      <span className="absolute bottom-[2px] left-[-4px] right-[-4px] h-[40%] rounded-[8px] -z-10 bg-honey-tint" />
      {children}
    </span>
  );
}

export function Card({ children, className = "", hover = true }: { children: ReactNode; className?: string; hover?: boolean }) {
  return (
    <div className={`bg-surface-card rounded-card border border-border-subtle shadow-card p-7 ${hover ? "transition-all duration-base ease-standard hover:-translate-y-0.5 hover:shadow-card-hover hover:border-border-strong" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function BrandIconBadge({ children, variant = "honey" }: { children: ReactNode; variant?: "honey" | "petrol" | "danger" }) {
  const bg = variant === "danger" ? "bg-danger/10" : variant === "petrol" ? "bg-petrol-mist" : "bg-honey-tint";
  const color = variant === "danger" ? "text-danger" : variant === "petrol" ? "text-petrol-600" : "text-honey-500";
  return (
    <div className={`w-9 h-9 rounded-xl ${bg} flex items-center justify-center flex-shrink-0 ${color}`}>
      {children}
    </div>
  );
}

export function CheckBullet() {
  return (
    <div className="w-5 h-5 rounded-full bg-honey-tint flex items-center justify-center flex-shrink-0">
      <Check size={12} strokeWidth={2.5} className="text-honey-500" />
    </div>
  );
}

export function TooltipInline({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-flex ml-1 cursor-help" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)} onFocus={() => setShow(true)} onBlur={() => setShow(false)} tabIndex={0} role="button" aria-label={text}>
      <Info size={13} strokeWidth={1.75} className="text-text-muted" />
      <AnimatePresence>
        {show && (
          <motion.span initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }} className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 text-xs leading-relaxed text-charcoal-text bg-charcoal-900 rounded-lg shadow-lg border border-charcoal-border z-50">
            {text}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

export function ButtonPrimary({ children, onClick, type = "button", disabled = false, className = "" }: { children: ReactNode; onClick?: () => void; type?: "button" | "submit"; disabled?: boolean; className?: string }) {
  return (
    <motion.button type={type} onClick={onClick} disabled={disabled} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className={`bg-honey-500 text-charcoal-900 font-semibold rounded-button px-5 py-3 text-[15px] hover:bg-honey-400 focus:outline-none focus:shadow-honey-ring disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-fast ${className}`}>
      {children}
    </motion.button>
  );
}

export function ButtonSecondary({ children, onClick, href, className = "" }: { children: ReactNode; onClick?: () => void; href?: string; className?: string }) {
  const cls = `inline-flex items-center justify-center border border-border-strong text-text-primary font-semibold rounded-button px-5 py-3 text-[15px] hover:bg-honey-tint hover:border-honey-500/30 transition-all duration-fast ${className}`;
  if (href) return <a href={href} className={cls}>{children}</a>;
  return <button onClick={onClick} className={cls}>{children}</button>;
}

export function Input({ label, id, type = "text", required = false, value, onChange, placeholder }: { label: string; id: string; type?: string; required?: boolean; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-text-primary mb-1.5">{label}{required && <span className="text-danger ml-0.5">*</span>}</label>
      <input id={id} name={id} type={type} required={required} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-full bg-white border border-border-strong rounded-button px-3 py-3 text-[15px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-honey-500 focus:ring-2 focus:ring-honey-glow transition-colors duration-fast" aria-label={label} />
    </div>
  );
}

export function Select({ label, id, value, onChange, options, placeholder = "Select..." }: { label: string; id: string; value: string; onChange: (v: string) => void; options: readonly string[]; placeholder?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-text-primary mb-1.5">{label}</label>
      <select id={id} name={id} value={value} onChange={(e) => onChange(e.target.value)} className="w-full bg-white border border-border-strong rounded-button px-3 py-3 text-[15px] text-text-primary focus:outline-none focus:border-honey-500 focus:ring-2 focus:ring-honey-glow transition-colors duration-fast appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%237A7066%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_12px_center] bg-no-repeat" aria-label={label}>
        <option value="">{placeholder}</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

export function AvatarPlaceholder({ size = 40 }: { size?: number }) {
  return (
    <div className="rounded-full bg-border-subtle flex items-center justify-center flex-shrink-0 overflow-hidden" style={{ width: size, height: size }}>
      <User size={size * 0.5} strokeWidth={1.75} className="text-text-muted" />
    </div>
  );
}

export function scrollToForm() {
  document.getElementById("final-cta")?.scrollIntoView({ behavior: "smooth" });
}
