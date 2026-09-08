// Dev-only comparison of the mark variants -- mounted by dev/logo-lab.tsx,
// served by `vite dev` at /dev/logo-lab.html. Not part of the production
// build (vite build only takes the root index.html). Nothing links here;
// delete freely once a direction is chosen.
import { Logo } from "../src/components/Logo";

const VARIANTS = ["default", "wink-open", "wink-closed", "wink-closed-ascender"] as const;
const SIZES = [16, 28, 64, 180];

const THEMES = [
  { name: "light", bg: "#ffffff", surface: "#ffffff", accent: "#1f9d55", text: "#16211b" },
  { name: "dark", bg: "#121815", surface: "#19221e", accent: "#3ecb79", text: "#ecf3ef" },
];

function ThemePanel({ theme }: { theme: (typeof THEMES)[number] }) {
  return (
    <section
      style={{
        background: theme.bg,
        color: theme.text,
        padding: "1.5rem",
        borderRadius: 12,
        flex: "1 1 360px",
      }}
    >
      <h2 style={{ font: "600 0.9rem/1.2 system-ui", margin: "0 0 1rem", opacity: 0.7 }}>
        {theme.name}
      </h2>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th />
            {SIZES.map((s) => (
              <th
                key={s}
                style={{ font: "500 0.75rem system-ui", padding: "0.25rem 0.5rem", opacity: 0.6 }}
              >
                {s}px
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {VARIANTS.map((variant) => (
            <tr key={variant}>
              <td style={{ font: "500 0.8rem system-ui", padding: "0.6rem 0.75rem 0.6rem 0", whiteSpace: "nowrap" }}>
                {variant}
              </td>
              {SIZES.map((size) => (
                <td key={size} style={{ padding: "0.6rem 0.5rem", textAlign: "center" }}>
                  <span
                    style={{
                      display: "inline-flex",
                      padding: 6,
                      borderRadius: 8,
                      background: theme.surface,
                      color: theme.accent,
                    }}
                  >
                    <Logo size={size} variant={variant} />
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: "1.25rem", display: "flex", gap: "1rem", alignItems: "center" }}>
        {VARIANTS.map((variant) => (
          <span
            key={variant}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.3em",
              font: "1.5rem/1 'Manrope Variable', system-ui",
              letterSpacing: "-0.01em",
            }}
          >
            <Logo size={28} variant={variant} className="wordmark-mark" />
            <span>
              <span style={{ color: theme.accent, fontWeight: 700 }}>good</span>
              <span style={{ color: theme.text, fontWeight: 400 }}>gorithm</span>
            </span>
          </span>
        ))}
      </div>
    </section>
  );
}

export function LogoLab() {
  return (
    <main style={{ font: "400 14px system-ui", padding: "2rem", maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ font: "700 1.4rem system-ui", margin: "0 0 0.5rem" }}>Mark variants</h1>
      <p style={{ margin: "0 0 2rem", opacity: 0.7 }}>
        <code>Logo</code> <code>variant</code> prop. The wink takes shift the whole <code>g</code>{" "}
        right so its bowl is the right eye, add a soft closed left eye, and run the descender under
        both as a smile — no node accents. <code>wink-open</code> keeps the bowl gap;{" "}
        <code>wink-closed</code> is a full ring; <code>wink-closed-ascender</code> adds a small
        ear off its top-right. Does it read as a wink at 16px — and still as a <code>g</code>?
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem" }}>
        {THEMES.map((theme) => (
          <ThemePanel key={theme.name} theme={theme} />
        ))}
      </div>
    </main>
  );
}

