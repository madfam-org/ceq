import { describe, expect, it } from "vitest";

import {
  BENCHMARK_MODELS,
  MODALITY_ORDER,
  bestValueScore,
  groupByModality,
  licenseSignal,
  runsInComfyUI,
  vramEfficiency,
  type BenchmarkModel,
  type LicenseClass,
} from "@/lib/benchmarks";

describe("benchmarks seed dataset", () => {
  it("has unique model ids", () => {
    const ids = BENCHMARK_MODELS.map((m) => m.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("covers every modality with at least one model", () => {
    for (const modality of MODALITY_ORDER) {
      const count = BENCHMARK_MODELS.filter(
        (m) => m.modality === modality,
      ).length;
      expect(count, `modality ${modality} has models`).toBeGreaterThan(0);
    }
  });

  it("keeps commercialOk consistent with license class", () => {
    for (const model of BENCHMARK_MODELS) {
      const cleanClass =
        model.licenseClass !== "non-commercial" &&
        model.licenseClass !== "api-only";
      // Non-commercial / api-only can never be commercially OK.
      if (!cleanClass) {
        expect(model.commercialOk, `${model.id} is not commercial`).toBe(false);
      }
    }
  });

  it("gives every model a verified date and source url", () => {
    for (const model of BENCHMARK_MODELS) {
      expect(model.sourceUrl).toMatch(/^https?:\/\//);
      expect(model.verifiedDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });
});

describe("licenseSignal", () => {
  const cases: Array<[LicenseClass, "green" | "amber" | "red"]> = [
    ["apache", "green"],
    ["mit", "green"],
    ["openrail", "green"],
    ["revenue-gated", "amber"],
    ["geo-gated", "amber"],
    ["non-commercial", "red"],
    ["api-only", "red"],
  ];
  it.each(cases)("maps %s to %s", (licenseClass, expected) => {
    expect(licenseSignal(licenseClass)).toBe(expected);
  });
});

describe("runsInComfyUI", () => {
  it("is false only for api-only models", () => {
    const apiOnly = { comfyuiRating: "api-only" } as BenchmarkModel;
    const dropIn = { comfyuiRating: "drop-in" } as BenchmarkModel;
    expect(runsInComfyUI(apiOnly)).toBe(false);
    expect(runsInComfyUI(dropIn)).toBe(true);
  });
});

describe("vramEfficiency", () => {
  it("treats CPU-capable (null) as maximally efficient", () => {
    expect(vramEfficiency(null)).toBe(1);
  });

  it("scores <=8GB at the top and clamps large models to the floor", () => {
    expect(vramEfficiency(6)).toBe(1);
    expect(vramEfficiency(8)).toBe(1);
    expect(vramEfficiency(64)).toBe(0.3);
  });

  it("falls off monotonically between 8GB and 48GB", () => {
    expect(vramEfficiency(16)).toBeGreaterThan(vramEfficiency(32));
    expect(vramEfficiency(32)).toBeGreaterThan(vramEfficiency(48));
  });
});

describe("bestValueScore", () => {
  it("rewards a clean-license drop-in efficiency pick over a gated needs-build", () => {
    const kokoro = BENCHMARK_MODELS.find((m) => m.id === "kokoro-82m")!;
    const emu = BENCHMARK_MODELS.find((m) => m.id === "emu3-5")!;
    expect(bestValueScore(kokoro)).toBeGreaterThan(bestValueScore(emu));
  });

  it("returns a score in the 0-100 range for every model", () => {
    for (const model of BENCHMARK_MODELS) {
      const score = bestValueScore(model);
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(100);
    }
  });
});

describe("groupByModality", () => {
  it("groups in modality order and sorts standardize-now first", () => {
    const groups = groupByModality();
    const modalities = groups.map((g) => g.modality);
    // Order is a subsequence of MODALITY_ORDER.
    const expectedOrder = MODALITY_ORDER.filter((m) => modalities.includes(m));
    expect(modalities).toEqual(expectedOrder);

    for (const group of groups) {
      const tiers = group.models.map((m) => m.tier);
      const firstWatch = tiers.indexOf("watch");
      const lastNonWatch = tiers.lastIndexOf("standardize-now");
      if (firstWatch !== -1 && lastNonWatch !== -1) {
        expect(firstWatch).toBeGreaterThan(lastNonWatch);
      }
    }
  });

  it("drops empty groups when the input is filtered", () => {
    const onlyImage = BENCHMARK_MODELS.filter((m) => m.modality === "image");
    const groups = groupByModality(onlyImage);
    expect(groups).toHaveLength(1);
    expect(groups[0].modality).toBe("image");
  });
});
