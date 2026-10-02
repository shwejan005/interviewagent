import { expect, test } from "@playwright/test"

const recruiter = {
  user_id: 8,
  email: "recruiter@example.com",
  full_name: "Recruiter",
  is_platform_admin: false,
  active_org_id: 4,
  active_role: "org_owner",
  capabilities: ["campaign:read_org", "campaign:create", "campaign:update", "application:read"],
  memberships: [{ org_id: 4, org_name: "Acme", org_slug: "acme", role_name: "org_owner" }],
}

const candidate = {
  user_id: 9,
  email: "candidate@example.com",
  full_name: "Candidate",
  is_platform_admin: false,
  active_org_id: null,
  active_role: "candidate",
  capabilities: [],
  memberships: [],
}

const profile = {
  id: 1,
  user_id: 9,
  headline: "Backend Engineer",
  summary: "",
  location: "",
  phone: "",
  work_authorization: "",
  years_experience: null,
  open_to_work: true,
  is_discoverable: false,
  resume_text: "",
  data_consent_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  experiences: [],
  education: [],
  skills: [],
  preferences: null,
  vault_answers: {},
}

async function seedToken(page: import("@playwright/test").Page) {
  await page.addInitScript(() => window.localStorage.setItem("evalia_token", "test-token"))
}

test("recruiter login lands in the recruiter overview with existing campaigns", async ({ page }) => {
  await page.route("**/api/auth/login", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: "test-token", expires_in: 3600 }) }))
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(recruiter) }))
  await page.route("**/api/orgs/4/campaigns**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ campaigns: [{ id: 11, org_id: 4, name: "Platform expansion", description: "", status: "ACTIVE", department: "Engineering", hiring_manager: "", priority: "HIGH", target_hires: 3, target_close_date: null, created_at: "2026-09-30T00:00:00Z", posting_count: 2, applicant_count: 5 }] }),
  }))

  await page.goto("/login")
  await page.getByLabel("EMAIL").fill("recruiter@example.com")
  await page.getByLabel("PASSWORD").fill("correct-horse-battery")
  await page.getByRole("button", { name: "Log in" }).click()

  await page.waitForURL(/\/org$/, { timeout: 15_000 })
  await expect(page.getByRole("heading", { name: "Hiring operations" })).toBeVisible()
  await expect(page.getByText("Platform expansion")).toBeVisible()
  await expect(page.getByRole("link", { name: "Jobs" })).toHaveCount(0)
})

test("candidate profile uses the shared dark navigation instead of the light workspace shell", async ({ page }) => {
  await seedToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidate) }))
  await page.route("**/api/me/profile", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(profile) }))

  await page.goto("/profile")
  await expect(page.getByRole("link", { name: "Jobs" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Import resume" })).toBeVisible()
  await expect(page.getByText("Candidate workspace")).toHaveCount(0)
})
