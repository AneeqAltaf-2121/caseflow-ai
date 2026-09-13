import { defineConfig, devices } from "@playwright/test";

// Phase 41 end-to-end tests. Runs against an *already-running* stack —
// either `docker compose up` (Phase 39: web on :3000, api on :8000) or
// two manually-started dev/production servers — rather than spawning
// its own via Playwright's `webServer` option, so this config stays the
// same whether the stack is Docker Compose, a CI job's own two
// `docker compose`-started services, or a developer's local `next dev`
// + `uvicorn` pair. See e2e/README.md for exactly how to start both
// before running `npm run test:e2e`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
