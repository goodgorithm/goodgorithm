// Gives each feed card a barely-there background tint so the column reads
// as gentle rhythm rather than one uniform slab. The tint is a stable hash
// of the post id -- pure visual variation, no meaning, no category
// coupling. The values themselves are the --card-tint-* pairs in theme.css
// (light + dark); PostCard applies the pick as an inline --card-tint custom
// property, and .card falls back to --color-surface when it's unset.

const TINT_COUNT = 5;

// FNV-1a over the id string -> a stable bucket in [1, TINT_COUNT]. Math.imul
// keeps the multiply in 32-bit; `>>> 0` back to unsigned before the modulo.
export function cardTintVar(id: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return `var(--card-tint-${((hash >>> 0) % TINT_COUNT) + 1})`;
}
