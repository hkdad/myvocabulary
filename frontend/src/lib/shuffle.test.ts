import { describe, expect, it } from "vitest";

import { shuffleArray } from "./shuffle";

describe("shuffleArray", () => {
  it("returns a permutation of the input", () => {
    const input = [1, 2, 3, 4, 5];
    const shuffled = shuffleArray(input);
    expect(shuffled).toHaveLength(input.length);
    expect(shuffled.sort()).toEqual(input.sort());
    expect(input).toEqual([1, 2, 3, 4, 5]);
  });
});
