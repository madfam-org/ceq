import { LiveDemoSection } from "@/components/landing/live-demo-section";
import { WorkflowShowcaseSection } from "@/components/landing/workflow-showcase-section";
import Link from "next/link";

export default function ExperiencePage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border/50 bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="font-mono text-xl font-bold gradient-text">
            ceq
          </Link>
          <Link
            href="/#pricing"
            className="font-mono text-sm text-muted-foreground hover:text-foreground"
          >
            Pricing
          </Link>
        </div>
      </header>
      <LiveDemoSection />
      <WorkflowShowcaseSection />
    </div>
  );
}
