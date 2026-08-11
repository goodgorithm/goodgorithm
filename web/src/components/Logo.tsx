// The settled lowercase-g mark - see CLAUDE.md's Visual identity section
// for the exact path data and the rationale behind it.
export function Logo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M 66.13 44.45 A 20 20 0 1 1 66.13 27.55"
        fill="none"
        stroke="currentColor"
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M 55 55 C 57 76, 34 94, 16 82"
        fill="none"
        stroke="currentColor"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <circle cx="66.13" cy="44.45" r="6" fill="currentColor" />
      <circle cx="66.13" cy="27.55" r="6" fill="currentColor" />
      <circle cx="16" cy="82" r="6" fill="currentColor" />
    </svg>
  );
}
