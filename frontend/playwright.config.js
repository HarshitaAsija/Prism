import { defineConfig } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
const dataDir = path.resolve("../work/browser-tests");
fs.mkdirSync(dataDir, { recursive: true });
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  retries: 0,
  timeout: 60000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROME
      ? { executablePath: process.env.PLAYWRIGHT_CHROME }
      : {},
  },
  webServer: [
    {
      command: `"${process.env.PRISM_PYTHON ? path.resolve(process.env.PRISM_PYTHON) : "python"}" -m uvicorn main:app --app-dir ../backend --host 127.0.0.1 --port 8001`,
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      env: {
        PRISM_DB_PATH: path.join(dataDir, `test-${Date.now()}.db`),
        CORS_ORIGINS: "http://127.0.0.1:5173",
        NVIDIA_API_KEY: "",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      env: { VITE_API_URL: "http://127.0.0.1:8001" },
    },
  ],
});
