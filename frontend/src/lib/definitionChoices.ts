export type DefinitionChoice = {
  definition: string;
  definition_zh_hant: string | null;
  entry_id?: number;
};

const FALLBACK_DEFINITIONS: DefinitionChoice[] = [
  { definition: "A place where you can borrow books.", definition_zh_hant: "可以借書的地方。" },
  { definition: "To move quickly using your legs.", definition_zh_hant: "用雙腿快速移動。" },
  { definition: "A large animal with a long trunk.", definition_zh_hant: "有長鼻的大型動物。" },
  { definition: "Water that falls from clouds.", definition_zh_hant: "從雲層落下的水。" },
  { definition: "A sweet fruit that grows on trees.", definition_zh_hant: "長在樹上的甜味水果。" },
  { definition: "A person who teaches students.", definition_zh_hant: "教導學生的人。" },
];

function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function shuffle<T>(items: T[], random: () => number): T[] {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
  }
  return copy;
}

function choiceKey(choice: DefinitionChoice | string): string {
  const definition = typeof choice === "string" ? choice : choice.definition;
  return definition.trim().toLowerCase();
}

/** Match definitions the same way distractors are filtered when building MCQ options. */
export function definitionsMatch(left: string, right: string): boolean {
  return choiceKey(left) === choiceKey(right);
}

/**
 * Build MCQ options. Correct answer is inserted at a uniformly random slot
 * (or deterministic slot when `seed` is set for tests).
 */
export function generateDefinitionChoices(
  correct: DefinitionChoice,
  pool: DefinitionChoice[],
  count = 4,
  seed?: number,
): DefinitionChoice[] {
  const normalizedCorrect = choiceKey(correct);
  const distractors = pool.filter((item) => choiceKey(item) !== normalizedCorrect);

  const paddedPool = [...distractors];
  for (const fallback of FALLBACK_DEFINITIONS) {
    if (paddedPool.length >= count - 1) {
      break;
    }
    if (choiceKey(fallback) !== normalizedCorrect) {
      paddedPool.push(fallback);
    }
  }

  const random = seed == null ? Math.random : seededRandom(seed);
  const picked = shuffle(paddedPool, random).slice(0, Math.max(0, count - 1));
  // Explicit slot — avoids Fisher–Yates + LCG bias that parked answers in one corner.
  const insertAt = Math.floor(random() * (picked.length + 1));
  const options = [...picked];
  options.splice(insertAt, 0, correct);
  return options;
}

export function applyZhToChoices(
  choices: DefinitionChoice[],
  zhByEntryId: Record<number, string>,
): DefinitionChoice[] {
  return choices.map((choice) => {
    if (choice.entry_id == null) {
      return choice;
    }
    const zh = zhByEntryId[choice.entry_id];
    if (!zh) {
      return choice;
    }
    return { ...choice, definition_zh_hant: zh };
  });
}
