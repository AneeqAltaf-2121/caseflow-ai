import path from "node:path";
import { expect, test } from "@playwright/test";

// Phase 41: the full user journey the phase spec names, driven through
// real accessible-name locators against the app's actual markup (no
// test ids added anywhere) — login -> create project -> upload PDF ->
// wait for processing -> ask a question -> receive a grounded answer
// -> open the citation. Each run uses a fresh email/project name so it
// can run repeatedly against a persistent dev database without
// colliding with a previous run's data.

const SAMPLE_PDF = path.join(__dirname, "fixtures", "sample-contract.pdf");

test("login, upload a document, ask a question, and open its citation", async ({ page }) => {
  const runId = Date.now();
  const email = `e2e-${runId}@example.com`;
  const projectName = `E2E Project ${runId}`;

  // --- Login (mock/dev OAuth — see app/login/page.tsx) ---
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  // --- Create project ---
  await page.getByRole("link", { name: "View all" }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill(projectName);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name: projectName })).toBeVisible();
  await page.getByRole("link", { name: projectName }).click();
  await expect(page).toHaveURL(/\/projects\/[^/]+$/);

  // --- Upload a PDF ---
  await page.getByRole("link", { name: "Documents" }).click();
  await page.getByLabel("Upload document").setInputFiles(SAMPLE_PDF);
  await expect(page.getByText("sample-contract.pdf")).toBeVisible();

  // --- Wait for background ingestion to finish. The documents page
  // polls while anything is still "uploaded"/"processing" (Phase 55),
  // so the status badge flips to "ready" on its own — no manual
  // page.reload() needed here. ---
  await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 45_000 });

  // --- Ask a grounded question ---
  await page.getByRole("link", { name: "Chat" }).click();
  await page.getByRole("button", { name: "New chat" }).click();
  await page.getByPlaceholder("Ask a question…").fill("When does the agreement terminate?");
  await page.getByRole("button", { name: "Ask" }).click();

  // --- Receive a grounded answer with a citation, and open it ---
  const sourcesHeading = page.getByText("Sources", { exact: true });
  await expect(sourcesHeading).toBeVisible({ timeout: 30_000 });
  const citationLink = page.locator("a", { hasText: "sample-contract.pdf" }).first();
  await expect(citationLink).toBeVisible();
  await citationLink.click();
  await expect(page).toHaveURL(/\/documents$/);
});
