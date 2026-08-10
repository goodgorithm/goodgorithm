// @atcute/cbor ships "type": "module" with an "exports" map and no types
// entry that this project's moduleResolution ("node10"/classic, paired
// with commonjs output) knows how to follow -- TypeScript can't locate
// its real .d.ts files even though the package resolves fine at runtime
// via dynamic import(). An ambient declaration is the standard escape
// hatch for exactly this case, scoped to only the one function actually
// used here rather than widening moduleResolution (and its ESM/CJS
// interop rules) for the whole project.
declare module "@atcute/cbor" {
  export function decodeFirst(buf: Uint8Array): [value: unknown, remainder: Uint8Array];
}
