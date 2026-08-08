export interface Cursor {
  rank_score: number;
  id: string;
}

export function encodeCursor(cursor: Cursor): string {
  return Buffer.from(JSON.stringify(cursor), "utf8").toString("base64url");
}

export function decodeCursor(raw: string): Cursor {
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
  } catch {
    throw new Error("invalid cursor");
  }

  if (
    typeof parsed !== "object" ||
    parsed === null ||
    typeof (parsed as Cursor).rank_score !== "number" ||
    typeof (parsed as Cursor).id !== "string"
  ) {
    throw new Error("invalid cursor");
  }

  return parsed as Cursor;
}
