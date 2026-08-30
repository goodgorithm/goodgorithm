import { describe, expect, it } from "vitest";

import { buildAtomFeed } from "../../vite-plugins/updatesFeed";

const SAMPLE = `# Updates

Intro paragraph that must not appear in the feed.

## 2026-08-28 — Groundwork for native apps

Work started on **Capacitor** builds. See [the repo](https://github.com/goodgorithm/goodgorithm).

- one
- two

## 2026-08-01 — Tom & Jerry <ship> it

A line with a raw < and & in it.
`;

describe("buildAtomFeed", () => {
  it("emits one <entry> per dated heading, in document (newest-first) order", () => {
    const xml = buildAtomFeed(SAMPLE);
    expect(xml.match(/<entry>/g) ?? []).toHaveLength(2);
    expect(xml.indexOf("Groundwork for native apps")).toBeLessThan(xml.indexOf("Jerry"));
  });

  it("ignores content above the first dated heading", () => {
    expect(buildAtomFeed(SAMPLE)).not.toContain("must not appear");
  });

  it("sets feed <updated> to the newest entry's date", () => {
    expect(buildAtomFeed(SAMPLE)).toContain("<updated>2026-08-28T00:00:00Z</updated>");
  });

  it("derives a slugged tag: id per entry", () => {
    expect(buildAtomFeed(SAMPLE)).toContain(
      "<id>tag:goodgorithm.com,2026-08-28:groundwork-for-native-apps</id>",
    );
  });

  it("XML-escapes entry titles", () => {
    expect(buildAtomFeed(SAMPLE)).toContain("<title>Tom &amp; Jerry &lt;ship&gt; it</title>");
  });

  it("wraps entry HTML in CDATA and escapes ampersands inside links", () => {
    const xml = buildAtomFeed("## 2026-01-01 — L\n\nSee [x](https://e.com/?a=1&b=2).\n");
    expect(xml).toContain('<content type="html"><![CDATA[');
    expect(xml).toContain('href="https://e.com/?a=1&amp;b=2"');
  });

  it("escapes body markup so a literal ]]> can't terminate the CDATA early", () => {
    const xml = buildAtomFeed("## 2026-01-01 — L\n\nliteral ]]> here\n");
    const cdata = xml.slice(xml.indexOf("<![CDATA["), xml.indexOf("]]></content>") + 3);
    // the > is escaped, so the only ]]> left in the section is its terminator
    expect(cdata).toContain("]]&gt; here");
    expect(cdata.match(/]]>/g)).toHaveLength(1);
  });

  it("produces a valid, entry-less feed when nothing is dated yet", () => {
    const xml = buildAtomFeed("# Updates\n\nJust an intro, no entries yet.\n");
    expect(xml).not.toContain("<entry>");
    expect(xml).toContain("<updated>1970-01-01T00:00:00Z</updated>");
    expect(xml.startsWith('<?xml version="1.0" encoding="utf-8"?>')).toBe(true);
  });
});
