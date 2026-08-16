// Every numeric config knob in this service reads through here rather than
// a bare `Number(process.env.X ?? "default")` -- a typo'd Railway value
// (e.g. "5ooo") would otherwise silently become NaN, and things like
// setTimeout(fn, NaN) fail in confusing ways at runtime instead of loudly
// at startup. Called from top-level `const` declarations, so an invalid
// value throws as soon as the module is imported.
export function parseNumberEnv(name: string, defaultValue: number): number {
  const raw = process.env[name];
  if (raw === undefined) return defaultValue;

  // Number("") is 0, not NaN -- an explicitly-set-but-blank env var (a real
  // Railway failure mode, not just a hypothetical) would otherwise silently
  // become a valid-looking 0 instead of raising here.
  const value = raw.trim() === "" ? NaN : Number(raw);
  if (Number.isNaN(value)) {
    throw new Error(`Invalid ${name}: "${raw}" is not a number`);
  }
  return value;
}
