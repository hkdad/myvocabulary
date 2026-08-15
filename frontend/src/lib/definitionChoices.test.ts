import { describe, expect, it } from "vitest";

import { definitionsMatch, generateDefinitionChoices } from "./definitionChoices";

describe("definitionsMatch", () => {
  it("ignores case and surrounding whitespace", () => {
    expect(definitionsMatch(" A place with animals. ", "a place with animals.")).toBe(true);
    expect(definitionsMatch("A zoo.", "a zoo.")).toBe(true);
    expect(definitionsMatch("A zoo.", "A park.")).toBe(false);
  });
});

describe("generateDefinitionChoices", () => {
  it("includes the correct definition in the options", () => {
    const choices = generateDefinitionChoices(
      { definition: "A greeting.", definition_zh_hant: "問候語。" },
      [
        { definition: "A color.", definition_zh_hant: "顏色。" },
        { definition: "A number.", definition_zh_hant: "數字。" },
      ],
      4,
    );
    expect(choices.some((choice) => choice.definition === "A greeting.")).toBe(true);
    expect(choices).toHaveLength(4);
  });

  it("never duplicates the correct answer", () => {
    const choices = generateDefinitionChoices(
      { definition: "A greeting.", definition_zh_hant: "問候語。" },
      [
        { definition: "A greeting.", definition_zh_hant: "問候語。" },
        { definition: "A color.", definition_zh_hant: "顏色。" },
        { definition: "A number.", definition_zh_hant: "數字。" },
      ],
      4,
    );
    const matches = choices.filter((choice) => choice.definition === "A greeting.");
    expect(matches).toHaveLength(1);
  });

  it("pads with fallback distractors when the pool is small", () => {
    const choices = generateDefinitionChoices(
      { definition: "Only one.", definition_zh_hant: null },
      [],
      4,
    );
    expect(choices).toHaveLength(4);
    expect(choices.some((choice) => choice.definition === "Only one.")).toBe(true);
  });

  it("keeps option order stable for the same seed", () => {
    const correct = { definition: "A greeting.", definition_zh_hant: "問候語。", entry_id: 1 };
    const pool = [
      { definition: "A color.", definition_zh_hant: "顏色。", entry_id: 2 },
      { definition: "A number.", definition_zh_hant: "數字。", entry_id: 3 },
      { definition: "A fruit.", definition_zh_hant: "水果。", entry_id: 4 },
    ];
    const first = generateDefinitionChoices(correct, pool, 4, 42);
    const second = generateDefinitionChoices(correct, pool, 4, 42);
    expect(first.map((choice) => choice.definition)).toEqual(
      second.map((choice) => choice.definition),
    );
  });

  it("places the correct answer in every slot across seeds", () => {
    const correct = { definition: "A greeting.", definition_zh_hant: "問候語。", entry_id: 1 };
    const pool = [
      { definition: "A color.", definition_zh_hant: "顏色。", entry_id: 2 },
      { definition: "A number.", definition_zh_hant: "數字。", entry_id: 3 },
      { definition: "A fruit.", definition_zh_hant: "水果。", entry_id: 4 },
    ];
    const counts = [0, 0, 0, 0];
    for (let seed = 0; seed < 400; seed += 1) {
      const choices = generateDefinitionChoices(correct, pool, 4, seed);
      const index = choices.findIndex((choice) => choice.definition === "A greeting.");
      counts[index] += 1;
    }
    // Uniform insert — every slot must appear often (not ~0 for bottom-right).
    for (const count of counts) {
      expect(count).toBeGreaterThan(40);
    }
  });

  it("spreads the correct answer across slots with Math.random", () => {
    const correct = { definition: "A greeting.", definition_zh_hant: "問候語。", entry_id: 1 };
    const pool = [
      { definition: "A color.", definition_zh_hant: "顏色。", entry_id: 2 },
      { definition: "A number.", definition_zh_hant: "數字。", entry_id: 3 },
      { definition: "A fruit.", definition_zh_hant: "水果。", entry_id: 4 },
    ];
    const counts = [0, 0, 0, 0];
    for (let i = 0; i < 400; i += 1) {
      const choices = generateDefinitionChoices(correct, pool, 4);
      const index = choices.findIndex((choice) => choice.definition === "A greeting.");
      counts[index] += 1;
    }
    for (const count of counts) {
      expect(count).toBeGreaterThan(40);
    }
  });
});
