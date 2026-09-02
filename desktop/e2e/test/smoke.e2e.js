import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { expect } from "chai";
import { Builder, By, Capabilities, until } from "selenium-webdriver";


const __dirname = path.dirname(fileURLToPath(import.meta.url));
const defaultBinary = path.resolve(
  __dirname,
  "..",
  "..",
  "src-tauri",
  "target",
  "debug",
  process.platform === "win32" ? "petrolab-desktop.exe" : "petrolab-desktop",
);
const application = process.env.PETROLAB_E2E_BINARY || defaultBinary;

let driver;
let tauriDriver;

function waitForPort(port, host = "127.0.0.1", timeoutMs = 30000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.createConnection({ port, host });
      socket.once("connect", () => {
        socket.destroy();
        resolve();
      });
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() - started >= timeoutMs) {
          reject(new Error(`Timed out waiting for tauri-driver on ${host}:${port}`));
          return;
        }
        setTimeout(attempt, 250);
      });
    };
    attempt();
  });
}

async function screenTitle() {
  const heading = await driver.wait(until.elementLocated(By.css("header.topbar h2")), 15000);
  return heading.getText();
}

async function clickButtonContaining(text) {
  const button = await driver.wait(
    until.elementLocated(By.xpath(`//button[contains(normalize-space(.), ${JSON.stringify(text)})]`)),
    15000,
  );
  await driver.wait(until.elementIsEnabled(button), 15000);
  await button.click();
}

before(async function () {
  this.timeout(120000);

  tauriDriver = spawn("tauri-driver", [], {
    stdio: ["ignore", "inherit", "inherit"],
    shell: process.platform === "win32",
  });
  tauriDriver.once("error", (error) => {
    throw error;
  });

  await waitForPort(4444);

  const capabilities = new Capabilities();
  capabilities.set("tauri:options", { application });
  capabilities.setBrowserName("wry");

  driver = await new Builder()
    .withCapabilities(capabilities)
    .usingServer("http://127.0.0.1:4444/")
    .build();
});

after(async function () {
  this.timeout(30000);
  if (driver) {
    await driver.quit().catch(() => {});
  }
  if (tauriDriver && !tauriDriver.killed) {
    tauriDriver.kill();
  }
});

describe("PetroLab real desktop smoke", () => {
  it("opens the import workspace", async () => {
    expect(await screenTitle()).to.equal("Импорт");
    const chooseFile = await driver.wait(
      until.elementLocated(By.xpath("//button[contains(normalize-space(.), 'Выбрать файл')]")),
      15000,
    );
    expect(await chooseFile.isDisplayed()).to.equal(true);
  });

  it("navigates to Analyses and back through Add data", async () => {
    await clickButtonContaining("Анализы");
    await driver.wait(async () => (await screenTitle()) === "Анализы", 15000);

    await clickButtonContaining("Добавить данные");
    await driver.wait(async () => (await screenTitle()) === "Импорт", 15000);

    const chooseFile = await driver.wait(
      until.elementLocated(By.xpath("//button[contains(normalize-space(.), 'Выбрать файл')]")),
      15000,
    );
    expect(await chooseFile.isDisplayed()).to.equal(true);
  });
});
