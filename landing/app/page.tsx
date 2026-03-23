import { Navbar } from "@/components/Navbar";
import { Hero } from "@/components/Hero";
import { StatsStrip } from "@/components/StatsStrip";
import { HeroProofStrip } from "@/components/SocialProof";
import { ProblemSolutionBand } from "@/components/ProblemSolution";
import { HowItWorks } from "@/components/HowItWorks";
import { WhatYouGet } from "@/components/WhatYouGet";
import { FeatureDeepDive } from "@/components/FeatureDeepDive";
import { Proof } from "@/components/Proof";
import { CaseStudyCarousel } from "@/components/CaseStudies";
import { CoverageBand } from "@/components/CoverageBand";
import { Pricing } from "@/components/Pricing";
import { FAQAccordion } from "@/components/FAQ";
import { FinalCTAForm, Footer } from "@/components/FinalCTA";

export default function LandingPage() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <StatsStrip />
        <HeroProofStrip />
        <ProblemSolutionBand />
        <HowItWorks />
        <WhatYouGet />
        <FeatureDeepDive />
        <Proof />
        <CaseStudyCarousel />
        <CoverageBand />
        <Pricing />
        <FAQAccordion />
        <FinalCTAForm />
      </main>
      <Footer />
    </>
  );
}
