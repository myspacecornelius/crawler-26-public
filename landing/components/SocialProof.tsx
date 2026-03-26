"use client";

import { TESTIMONIALS, type Testimonial } from "./constants";
import { AvatarPlaceholder, Container } from "./primitives";

export function MicroProof({ testimonial, className = "" }: { testimonial: Testimonial; className?: string }) {
  return (
    <div className={`flex items-center gap-4 bg-surface-primary border border-border-subtle rounded-card px-6 py-4 shadow-sm ${className}`}>
      <div className="w-1 h-10 bg-honey-500 rounded-full flex-shrink-0" />
      <blockquote className="text-sm text-text-secondary leading-relaxed italic flex-1">&ldquo;{testimonial.quote}&rdquo;</blockquote>
      <div className="flex items-center gap-2 flex-shrink-0">
        <AvatarPlaceholder size={32} />
        <div>
          <div className="text-[13px] font-semibold text-text-primary">{testimonial.name}</div>
          <div className="text-[12px] text-text-secondary">{testimonial.role}, {testimonial.city}</div>
        </div>
      </div>
    </div>
  );
}

export function SidecarTestimonial({ testimonial, stat, statLabel }: { testimonial: Testimonial; stat: string; statLabel: string }) {
  return (
    <div className="bg-charcoal-800 rounded-card p-6 text-white border border-charcoal-border">
      <div className="flex items-center gap-3 mb-4">
        <div className="text-3xl font-[700] text-honey-500">{stat}</div>
        <div className="text-[12px] text-white/60 uppercase tracking-wider leading-tight">{statLabel}</div>
      </div>
      <blockquote className="text-sm text-white/80 leading-relaxed mb-4">&ldquo;{testimonial.quote}&rdquo;</blockquote>
      <div className="flex items-center gap-2">
        <AvatarPlaceholder size={28} />
        <div>
          <div className="text-[13px] font-semibold text-white/90">{testimonial.name}</div>
          <div className="text-[12px] text-white/60">{testimonial.role} ({testimonial.stage}), {testimonial.city}</div>
        </div>
      </div>
    </div>
  );
}

export function HeroProofStrip() {
  return (
    <div className="py-6 border-y border-border-subtle bg-surface-warm">
      <Container>
        <MicroProof testimonial={TESTIMONIALS[0]} />
      </Container>
    </div>
  );
}
