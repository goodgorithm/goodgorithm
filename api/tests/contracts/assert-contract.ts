// Dependency-free structural checker for android-feed-contract.ts. Asserts a
// value conforms to a named contract type: every field the contract lists
// must be present and type-compatible; EXTRA fields on the value are allowed
// (forward-compatible - the frozen app just ignores them). See that file's
// header for the field-string grammar.

type Contract = Record<string, unknown>;

export function assertConformsToContract(
  value: unknown,
  typeName: string,
  contract: Contract,
  path: string = typeName,
): void {
  const spec = contract[typeName];
  if (spec === undefined) {
    throw new Error(`contract has no type "${typeName}"`);
  }
  assertValue(value, spec, contract, path);
}

function assertValue(value: unknown, spec: unknown, contract: Contract, path: string): void {
  if (typeof spec === "string") {
    assertFieldSpec(value, spec, contract, path);
    return;
  }
  if (isRecord(spec) && typeof spec.__union === "string") {
    assertUnion(value, spec, contract, path);
    return;
  }
  if (isRecord(spec)) {
    assertObject(value, spec, contract, path);
    return;
  }
  throw new Error(`${path}: malformed contract spec ${JSON.stringify(spec)}`);
}

function assertFieldSpec(value: unknown, spec: string, contract: Contract, path: string): void {
  if (spec.endsWith("[]")) {
    const inner = spec.slice(0, -2);
    if (!Array.isArray(value)) {
      throw new Error(`${path}: expected ${spec}, got ${describe(value)}`);
    }
    value.forEach((el, i) => assertFieldSpec(el, inner, contract, `${path}[${i}]`));
    return;
  }
  if (spec.endsWith("|null")) {
    if (value === null) return;
    assertFieldSpec(value, spec.slice(0, -"|null".length), contract, path);
    return;
  }
  if (spec === "string" || spec === "number" || spec === "boolean") {
    if (typeof value !== spec || value === null) {
      throw new Error(`${path}: expected ${spec}, got ${describe(value)}`);
    }
    return;
  }
  if (spec in contract) {
    assertConformsToContract(value, spec, contract, path);
    return;
  }
  throw new Error(`${path}: contract references unknown type "${spec}"`);
}

function assertUnion(
  value: unknown,
  spec: Record<string, unknown>,
  contract: Contract,
  path: string,
): void {
  if (!isRecord(value)) {
    throw new Error(`${path}: expected a discriminated-union object, got ${describe(value)}`);
  }
  const discriminant = spec.__union as string;
  const tag = value[discriminant];
  if (typeof tag !== "string") {
    throw new Error(`${path}.${discriminant}: expected a string discriminant, got ${describe(tag)}`);
  }
  const sub = spec[tag];
  // Lenient: a discriminant value this contract doesn't list is a NEW union
  // member the frozen app doesn't know - it renders nothing for it and
  // carries on, so this is not a contract break. Only known members are
  // shape-checked.
  if (sub === undefined) return;
  assertObject(value, sub as Record<string, unknown>, contract, `${path}(${discriminant}=${tag})`);
}

function assertObject(
  value: unknown,
  spec: Record<string, unknown>,
  contract: Contract,
  path: string,
): void {
  if (!isRecord(value)) {
    throw new Error(`${path}: expected an object, got ${describe(value)}`);
  }
  for (const key of Object.keys(spec)) {
    if (key === "__union") continue;
    if (!(key in value)) {
      throw new Error(`${path}.${key}: missing (required by the frozen contract)`);
    }
    assertValue(value[key], spec[key], contract, `${path}.${key}`);
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function describe(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  return typeof v;
}
