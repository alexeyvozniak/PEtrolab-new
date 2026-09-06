import { mkdir } from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { expect } from "chai";
import { Builder, By, Capabilities, until } from "selenium-webdriver";

const here = path.dirname(fileURLToPath(import.meta.url));
const artifacts = path.resolve(here, "..", "artifacts");
const binary = process.env.PETROLAB_E2E_BINARY || path.resolve(
  here, "..", "..", "src-tauri", "target", "debug",
  process.platform === "win32" ? "petrolab-desktop.exe" : "petrolab-desktop",
);
let driver;
let bridge;

function waitForPort(port, timeoutMs = 30000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.createConnection({ port, host: "127.0.0.1" });
      socket.once("connect", () => { socket.destroy(); resolve(); });
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() - started >= timeoutMs) reject(new Error(`Timed out waiting for tauri-driver on ${port}`));
        else setTimeout(attempt, 250);
      });
    };
    attempt();
  });
}

async function heading() {
  const node = await driver.wait(until.elementLocated(By.css("header.topbar h2")), 15000);
  return node.getText();
}

async function click(text) {
  const node = await driver.wait(until.elementLocated(By.xpath(`//button[contains(normalize-space(.), ${JSON.stringify(text)})]`)), 15000);
  await driver.wait(until.elementIsEnabled(node), 15000);
  await node.click();
}

before(async function () {
  this.timeout(120000);
  await mkdir(artifacts, { recursive: true });
  // Explicit native-driver wiring prevents Selenium from treating PetroLab.exe as Edge.
  bridge = spawn("tauri-driver", ["--port", "4444", "--native-driver", "msedgedriver.exe"], { stdio: "inherit", shell: process.platform === "win32" });
  await waitForPort(4444);
  const capabilities = new Capabilities();
  capabilities.setBrowserName("wry");
  capabilities.set("tauri:options", { application: binary });
  driver = await new Builder().usingServer("http://127.0.0.1:4444/").withCapabilities(capabilities).build();
});

after(async function () {
  if (driver) {
    await driver.takeScreenshot().then((png) => import("node:fs/promises").then(({ writeFile }) => writeFile(path.join(artifacts, "native-final.png"), png, "base64"))).catch(() => {});
    await driver.quit().catch(() => {});
  }
  bridge?.kill();
});

describe("PetroLab native desktop flow", () => {
  it("opens Import and exposes the real file-selection action", async () => {
    expect(await heading()).to.equal("Импорт");
    const choose = await driver.wait(until.elementLocated(By.xpath("//button[contains(normalize-space(.), 'Выбрать файл')]")), 15000);
    expect(await choose.isDisplayed()).to.equal(true);
  });

  it("clicks Analyses and returns to Import through Add data", async () => {
    await click("Анализы");
    await driver.wait(async () => (await heading()) === "Анализы", 15000);
    await click("Добавить данные");
    await driver.wait(async () => (await heading()) === "Импорт", 15000);
  });
});
