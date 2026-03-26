"use client";

import { Linkedin } from "lucide-react";
import { HoneypotMark } from "./icons";
import { Container } from "./primitives";

export function Footer() {
  return (
    <footer className="bg-charcoal-900 border-t border-charcoal-border py-8">
      <Container>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <a href="#" className="flex items-center gap-1.5 text-charcoal-text/60 hover:text-charcoal-text/80 transition-colors">
              <HoneypotMark size={12} className="text-charcoal-text/50" /><span className="text-[13px] font-semibold">Honeypot</span>
            </a>
            <a href="mailto:hello@honeypot.vc" className="text-charcoal-text/50 hover:text-charcoal-text/70 text-[13px] transition-colors">hello@honeypot.vc</a>
            <a href="#" aria-label="LinkedIn" className="text-charcoal-text/50 hover:text-charcoal-text/70 transition-colors"><Linkedin size={14} strokeWidth={1.75} /></a>
            <a href="#" className="text-charcoal-text/50 hover:text-charcoal-text/70 text-[13px] transition-colors">Privacy Policy</a>
          </div>
          <p className="text-charcoal-text/40 text-[12px] text-center md:text-right max-w-md">We provide research and advisory support; we do not guarantee fundraising outcomes.</p>
        </div>
      </Container>
    </footer>
  );
}
