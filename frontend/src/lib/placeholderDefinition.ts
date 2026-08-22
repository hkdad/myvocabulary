export const PLACEHOLDER_DEFINITION_PREFIX = "Definition pending";

export function isPlaceholderDefinition(definition: string): boolean {
  return definition.trim().toLowerCase().startsWith(PLACEHOLDER_DEFINITION_PREFIX.toLowerCase());
}
