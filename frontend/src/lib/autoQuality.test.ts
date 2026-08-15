import { describe, expect, it } from "vitest";

import { qualityFromDefinitionPick } from "./autoQuality";

describe("qualityFromDefinitionPick", () => {
  it("maps a correct pick to Good (4)", () => {
    expect(qualityFromDefinitionPick(true)).toBe(4);
  });

  it("maps a wrong pick to Wrong (1)", () => {
    expect(qualityFromDefinitionPick(false)).toBe(1);
  });
});
