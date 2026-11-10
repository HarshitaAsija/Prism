import path from "node:path";
import { test, expect } from "@playwright/test";
const suffix = Date.now();
const password = "test-browser-password";
const errors = [];
async function registerWithApi(context, role, label) {
  const email = `${label}-${suffix}@example.com`;
  const response = await context.request.post(
    "http://127.0.0.1:8001/auth/register",
    { data: { name: `${label} User`, email, password, role } },
  );
  expect(response.status()).toBe(201);
  return { ...(await response.json()), email };
}
async function openWorkspace(page) {
  await page.goto("/");
  await page
    .getByRole("button", { name: /dashboard|workspace/i })
    .first()
    .click();
}
test("candidate signs up in the browser, saves their profile and retains it after reload", async ({
  page,
}) => {
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Get Started", exact: true }).click();
  await page
    .getByRole("button", { name: /Candidate.*looking for a job/ })
    .click();
  await page.getByLabel("Full Name", { exact: true }).fill("Browser Candidate");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`signup-${suffix}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create Account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your candidate workspace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit profile", exact: true }).click();
  await page.getByLabel("Professional Title").fill("Backend Engineer");
  await page.getByLabel("Skills (comma separated)").fill("Python, Go");
  await page.getByLabel("GitHub URL").fill("https://github.com/example");
  await page.getByRole("button", { name: "Save Changes" }).click();
  await expect(
    page.getByText("Skills: Python, Go", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await openWorkspace(page);
  await expect(
    page.getByText("Skills: Python, Go", { exact: true }),
  ).toBeVisible();
  if (process.env.PRISM_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.PRISM_SCREENSHOT_DIR,"prism-candidate.png"),fullPage:true});
  expect(errors).toEqual([]);
});
test("recruiter posts a job and candidate applies through the UI", async ({
  browser,
}) => {
  const recruiter = await browser.newContext();
  await registerWithApi(recruiter, "recruiter", "recruiter");
  const rp = await recruiter.newPage();
  await openWorkspace(rp);
  await rp
    .getByRole("button", { name: "Hiring workspace", exact: true })
    .click();
  await rp.getByText("Post a job", { exact: true }).click();
  await rp.getByLabel("Job title", { exact: true }).fill("Platform Engineer");
  await rp.getByLabel("Company", { exact: true }).fill("Prism Test");
  await rp.getByLabel("Location or remote").fill("Remote");
  await rp
    .getByLabel("Required skills, separated by commas")
    .fill("Python, Go");
  await rp
    .getByLabel("Job description", { exact: true })
    .fill(
      "Build reliable Python services and maintain production infrastructure for our platform.",
    );
  await rp.getByRole("button", { name: "Publish job" }).click();
  await expect(
    rp.getByRole("heading", { name: "Platform Engineer", exact: true }),
  ).toBeVisible();
  const candidate = await browser.newContext();
  const user = await registerWithApi(candidate, "candidate", "applicant");
  await candidate.request.put(
    `http://127.0.0.1:8001/candidates/${user.candidate_id}`,
    {
      headers: { "X-Prism-Client": "web" },
      data: { title: "Engineer", skills: ["Python"] },
    },
  );
  const cp = await candidate.newPage();
  await openWorkspace(cp);
  await cp
    .getByRole("button", { name: "Jobs and applications", exact: true })
    .click();
  await cp.getByRole("button", { name: "Check skill coverage" }).click();
  await expect(
    cp.getByText("Missing skills: go", { exact: true }),
  ).toBeVisible();
  await cp.getByRole("button", { name: "Apply with my profile" }).click();
  await expect(cp.getByText("Your status:", { exact: false })).toBeVisible();
  await rp.getByRole("button", { name: "Refresh", exact: true }).click();
  await rp.getByRole("button", { name: "Move to screened" }).click();
  await rp.getByLabel("Internal recruiter note").fill("Internal evaluation");
  await rp.getByRole("button", { name: "Save note" }).click();
  await expect(
    rp.getByText("Internal evaluation", { exact: true }),
  ).toBeVisible();
  await cp.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(cp.getByText("screened", { exact: true })).toBeVisible();
  await expect(
    cp.getByText("Internal evaluation", { exact: true }),
  ).toHaveCount(0);
  await rp.getByText('Post a job', {exact:true}).click();
  await rp.evaluate(() => window.scrollTo(0,0));
  expect(await rp.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  if (process.env.PRISM_SCREENSHOT_DIR) await rp.screenshot({path:path.join(process.env.PRISM_SCREENSHOT_DIR,"prism-recruiter.png"),fullPage:true});
  await recruiter.close();
  await candidate.close();
});

test("recruiter navigation and hiring workspace fit a mobile viewport", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  await registerWithApi(context, "recruiter", "mobile");
  const page = await context.newPage();
  await openWorkspace(page);
  await page.getByLabel("Navigate workspace").selectOption("jobs");
  await expect(
    page.getByRole("heading", { name: "Hiring workspace", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  if (process.env.PRISM_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.PRISM_SCREENSHOT_DIR,"prism-mobile.png"),fullPage:true});
  await context.close();
});
