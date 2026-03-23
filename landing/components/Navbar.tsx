"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { HoneypotMark } from "./icons";
import { Container, ButtonPrimary, scrollToForm } from "./primitives";
import { NAV_LINKS } from "./constants";

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-charcoal-900 border-b border-charcoal-border no-print">
      <Container>
        <div className="flex items-center justify-between h-16">
          <a href="#" className="flex items-center gap-2 text-charcoal-text">
            <HoneypotMark size={18} className="text-honey-500" />
            <span className="font-[650] text-lg tracking-tight">Honeypot</span>
          </a>
          <div className="hidden md:flex items-center gap-6">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} className="text-charcoal-text/60 hover:text-charcoal-text text-sm font-medium transition-colors">{l.label}</a>
            ))}
            <a href="#final-cta" className="text-charcoal-text/60 hover:text-charcoal-text text-sm font-medium transition-colors">Book a call</a>
            <ButtonPrimary onClick={scrollToForm}>Get the list</ButtonPrimary>
          </div>
          <button onClick={() => setMobileOpen(!mobileOpen)} className="md:hidden text-charcoal-text p-2" aria-label="Toggle menu">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
              {mobileOpen ? <path d="M18 6L6 18M6 6l12 12" /> : <path d="M4 6h16M4 12h16M4 18h16" />}
            </svg>
          </button>
        </div>
        <AnimatePresence>
          {mobileOpen && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="md:hidden overflow-hidden border-t border-charcoal-border">
              <div className="py-4 flex flex-col gap-3">
                {NAV_LINKS.map((l) => (
                  <a key={l.href} href={l.href} onClick={() => setMobileOpen(false)} className="text-charcoal-text/60 hover:text-charcoal-text text-sm font-medium py-1">{l.label}</a>
                ))}
                <ButtonPrimary onClick={() => { setMobileOpen(false); scrollToForm(); }} className="mt-2 w-full">Get the list</ButtonPrimary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Container>
    </nav>
  );
}
