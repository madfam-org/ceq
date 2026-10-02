/**
 * The legal pages read their slug from `params`, which is a Promise on Next 15.
 * A page that forgot to await it would look up `PAGES[undefined]` and 404 every
 * legal route, so both halves are pinned here: known slugs render, unknown ones
 * call `notFound()`.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

import LegalPage, { generateStaticParams } from "@/app/legal/[slug]/page";
import { notFound } from "next/navigation";

describe("legal/[slug] page", () => {
  it("prerenders every legal slug", () => {
    const slugs = generateStaticParams().map((p) => p.slug);
    expect(slugs).toEqual(
      expect.arrayContaining(["terms", "privacy", "acceptable-use"]),
    );
  });

  it("awaits params and renders the requested page", async () => {
    const element = await LegalPage({ params: Promise.resolve({ slug: "terms" }) });
    render(element);
    expect(screen.getByRole("heading", { level: 1, name: "CEQ Terms" })).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });

  it("calls notFound() for an unknown slug", async () => {
    await expect(
      LegalPage({ params: Promise.resolve({ slug: "does-not-exist" }) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledTimes(1);
  });
});
