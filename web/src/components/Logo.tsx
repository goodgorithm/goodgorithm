// The lowercase-g mark - see CLAUDE.md's Visual identity section for the
// path data and the rationale.
//
// The g is shifted right within the viewBox so its (closed) bowl reads as
// a right eye; a soft closed left eye fills the freed space and the hooked
// descender runs under both as a smile, then tails off left. A small ear
// tops the ring's right side on the descender's line. The favicon / PWA /
// native-icon SVGs (web/public/, web/assets/) are authored separately and
// do not track this file automatically.
const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 9,
  strokeLinecap: "round",
} as const;

export function Logo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      aria-hidden="true"
    >
      <circle cx="68" cy="36" r="20" {...STROKE} />
      <path d="M 83 49 C 86 78, 48 96, 30 80" {...STROKE} />
      <path d="M 12 33 Q 21 41 30 33" {...STROKE} />
      <path d="M 88 26 L 90 14" {...STROKE} />
    </svg>
  );
}
