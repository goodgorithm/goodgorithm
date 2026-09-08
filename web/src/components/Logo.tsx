// The settled lowercase-g mark - see CLAUDE.md's Visual identity section
// for the exact path data and the rationale behind it.
//
// `variant` explores a winking-face reading: the whole g is shifted right
// (+18 on x) so its bowl becomes the right eye and its hooked descender
// runs under both eyes as a smile, and a soft closed left eye is added in
// the freed space. No node accents on the wink variants -- they read
// busier at the small sizes the mark is actually used at. "wink-open"
// keeps the current gap in the bowl; "wink-closed" is a full ring, which
// reads harder as a g; "wink-closed-ascender" adds a small ear where the
// descender's line, extended up, meets the ring. "default" is the shipped
// mark, untouched.
type LogoVariant = "default" | "wink-open" | "wink-closed" | "wink-closed-ascender";

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 9,
  strokeLinecap: "round",
} as const;

export function Logo({
  size = 24,
  className,
  variant = "default",
}: {
  size?: number;
  className?: string;
  variant?: LogoVariant;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      aria-hidden="true"
    >
      {variant === "default" ? <DefaultMark /> : <WinkMark variant={variant} />}
    </svg>
  );
}

function DefaultMark() {
  return (
    <>
      <path
        d="M 66.13 44.45 A 20 20 0 1 1 66.13 27.55"
        {...STROKE}
        strokeLinejoin="round"
      />
      <path d="M 55 55 C 57 76, 34 94, 16 82" {...STROKE} />
      <circle cx="66.13" cy="44.45" r="6" fill="currentColor" />
      <circle cx="66.13" cy="27.55" r="6" fill="currentColor" />
      <circle cx="16" cy="82" r="6" fill="currentColor" />
    </>
  );
}

// The g shifted +18 on x: right eye (bowl), descender-as-smile, plus a
// soft closed left eye. No nodes.
function WinkMark({
  variant,
}: {
  variant: "wink-open" | "wink-closed" | "wink-closed-ascender";
}) {
  const closed = variant !== "wink-open";
  // wink-closed*: the descender connects further right on the ring (a
  // truer g-tail) while still sweeping under the middle as a smile.
  const descender = closed
    ? "M 83 49 C 86 78, 48 96, 30 80"
    : "M 73 55 C 75 76, 52 94, 34 82";

  return (
    <>
      {closed ? (
        <circle cx="68" cy="36" r="20" {...STROKE} />
      ) : (
        <path
          d="M 84.13 44.45 A 20 20 0 1 1 84.13 27.55"
          {...STROKE}
          strokeLinejoin="round"
        />
      )}
      <path d={descender} {...STROKE} />
      <path d="M 12 33 Q 21 41 30 33" {...STROKE} />
      {/* small ear off the ring's top-right, on the descender's line
          extended up through the bowl -- the way a single-story g's ear
          continues its right-hand stem (cf. Manrope's g). Sits just off
          the outer edge so the round cap doesn't bleed into the bowl. */}
      {variant === "wink-closed-ascender" && <path d="M 88 26 L 90 14" {...STROKE} />}
    </>
  );
}
