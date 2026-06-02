# Landing Conversion Audit — CEQ (2026-06-02)

## Executive read

The current landing is now aligned to an outcome-first commercial message and does a
credible job translating CEQ’s technical strengths into user-facing business gains.
Compared with the previous version, it has materially higher conversion potential,
especially around free-to-pilot progression.

- **Overall conversion fit (current): 7.8 / 10**
- **Superpower clarity (current): 8.7 / 10**
- **Purchase intent activation (current): 7.2 / 10**

## What is already strong

1. **Pain-first framing is explicit.**
   The hero and the Superpower matrix describe actual operational pain (repeatable
   assets, cost uncertainty, sharing boundaries) before talking about features.

2. **Product proof is concrete.**
   The proof panel and simulated demo show structured prompts, output identifiers,
   cache-hit behavior, and cost accounting. This shortens the trust gap for first-time
   visitors who do not have API knowledge.

3. **CTA ladder is coherent for multiple buyer types.**
   - Start free CTA maps to experimentation.
   - Founding price CTA maps to individual buyers ready to commit.
   - Studio pilot CTA maps to teams with purchasing power and governance concerns.

4. **Commercial/legal surfacing exists on the landing.**
   Terms, privacy, acceptable use, retention, and refund paths are linked near the
   trust section. This reduces abandonment from risk-sensitive buyers.

5. **Founding intent capture is test-covered.**
   The landing now has explicit assertions in
   `apps/studio/__tests__/components/marketing-landing.test.tsx` for paid-intent
   framing and key conversion UI paths.

## What still blocks “immense desire” at enterprise-grade level

1. **No social proof yet (case studies/testimonials).**
   Serious buying teams respond to proof of outcome under constraint (time-to-first
   value and consistency gains), which is still under-represented.

2. **No explicit commercial urgency mechanism.**
   Scarcity messaging exists as copy (“founding”) but does not include deterministic
   constraints (capacity, cohort date, or limited seats) with visible progress.

3. **Manual checkout language still signals uncertainty.**
   The narrative around intent capture is transparent, but it still reads as
   pre-revenue gating instead of a reliable paid conversion pathway.

4. **Analytics wiring is under-specified for experimentation.**
   Events are tracked in-browser, but there is no connected data sink in the landing
   file itself. Conversion tuning needs reliable sink validation.

## Maximum-conversion recommendations (priority)

### P0 (high impact, low surface area)

1. Add a **single proof metric bar** above pricing with expected outcomes:
   "first usable repeatable asset under 15 minutes" and "stable reruns in 1 click."

2. Add **seat-capped urgency** (for both paid tiers):
   e.g., "7 pro seats, 2 studio pilot windows remaining this quarter."

3. Add a **3rd CTA row** on pricing that maps to next action after login:
   "Run a paid-path dry run with credits." This should remain disabled until credits
   and entitlement checks are complete.

### P1

4. Add **1–2 proof micro-stories** from real operators:
   role, workload type, and measurable gain (hours saved / repeats avoided).

5. Add **trust badges by workflow stage** (auth, callback, paid credits, gallery,
   support SLA) and link directly to evidence from launch readiness docs.

6. Replace non-quantified claims with **hard commitments**:
   e.g., "founder pricing locked for first run of paid cohort," "manual seat review in <24h."

### P2

7. Expand FAQ with **objection handling** around data governance, cancelability,
   and failure recovery cost.

8. Add first-party **conversion tracking schema** in a tiny shared module so all
   conversion events are queryable in one namespace.

## Landing optimization status after this release

- Completed: outcome-first structure, superpower matrix, cache-hit demo, conversion
  framing by buyer type, legal/commercial link surface, and intent capture tests.
- Pending before paid conversion claims scale:
  Dhanam checkout, entitlement proof, and production paid-path demonstration.

## Suggested rollout check

1. Ship this landing revision.
2. Capture desktop + mobile screenshot diffs for baseline.
3. Run Playwright smoke plus manual QA on CTA flow and event emission.
4. Add one micro social proof card and one scarcity block.
5. Capture conversion uplift by variant before toggling any pricing copy.
