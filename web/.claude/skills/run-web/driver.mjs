// Minimal chromium-cli-alike REPL driver for headless verification of web/.
// Not part of the app - agent tooling only. See SKILL.md.
//
// Reads newline-delimited commands from stdin, one per line:
//   nav <url>
//   wait-for text=<text>              (or a CSS selector)
//   screenshot [name]                 (default: 001.png, 002.png, ... in --out)
//   click text=<text>                 (or a CSS selector)
//   fill <selector> <value>
//   press <key>
//   eval <js-expression>              (result is JSON-printed)
//   console                           (dumps captured console errors/pageerrors)
//   scroll-bottom
//   reload
//   quit
//
// Usage: node driver.mjs --out <screenshot-dir> < commands.txt

import { chromium } from "playwright";
import { createInterface } from "node:readline";
import { mkdirSync } from "node:fs";

const outDir = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : ".";
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 500, height: 900 } });

const consoleLog = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleLog.push(`[console.error] ${msg.text()}`);
});
page.on("pageerror", (err) => consoleLog.push(`[pageerror] ${err}`));

let shotIndex = 0;

function targetLocator(arg) {
  if (arg.startsWith("text=")) return page.getByText(arg.slice(5));
  return page.locator(arg);
}

async function runCommand(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return;
  const [cmd, ...rest] = trimmed.split(" ");
  const arg = rest.join(" ");

  switch (cmd) {
    case "nav":
      await page.goto(arg);
      console.log(`ok nav ${arg}`);
      break;
    case "wait-for":
      await targetLocator(arg).first().waitFor({ timeout: 15000 });
      console.log(`ok wait-for ${arg}`);
      break;
    case "screenshot": {
      shotIndex += 1;
      const name = arg || String(shotIndex).padStart(3, "0");
      const path = `${outDir}/${name}.png`;
      await page.screenshot({ path });
      console.log(`ok screenshot ${path}`);
      break;
    }
    case "click":
      await targetLocator(arg).first().click();
      console.log(`ok click ${arg}`);
      break;
    case "fill": {
      const [selector, ...valueParts] = rest;
      await page.locator(selector).fill(valueParts.join(" "));
      console.log(`ok fill ${selector}`);
      break;
    }
    case "press":
      await page.keyboard.press(arg);
      console.log(`ok press ${arg}`);
      break;
    case "eval": {
      const result = await page.evaluate(arg);
      console.log(`ok eval ${JSON.stringify(result)}`);
      break;
    }
    case "scroll-bottom":
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      console.log("ok scroll-bottom");
      break;
    case "reload":
      await page.reload();
      console.log("ok reload");
      break;
    case "console":
      console.log(`console: ${JSON.stringify(consoleLog)}`);
      break;
    case "quit":
      await browser.close();
      process.exit(0);
      break;
    default:
      console.log(`err unknown command: ${cmd}`);
  }
}

const rl = createInterface({ input: process.stdin });
for await (const line of rl) {
  try {
    await runCommand(line);
  } catch (err) {
    console.log(`err ${err.message}`);
  }
}
await browser.close();
