import { expect, test } from "@playwright/test"

const candidateActor = {
  user_id: 7,
  email: "candidate@example.com",
  full_name: "Candidate",
  is_platform_admin: false,
  active_org_id: null,
  active_role: "candidate",
  capabilities: [],
  memberships: [],
}

const recruiterActor = {
  user_id: 8,
  email: "recruiter@example.com",
  full_name: "Recruiter",
  is_platform_admin: false,
  active_org_id: 4,
  active_role: "org_owner",
  capabilities: ["campaign:update", "application:read"],
  memberships: [{ org_id: 4, org_name: "Acme", org_slug: "acme", role_name: "org_owner" }],
}

const profile = {
  id: 2,
  user_id: 7,
  headline: "Backend Engineer",
  summary: "Builds reliable systems.",
  location: "Remote",
  phone: "",
  work_authorization: "",
  years_experience: 5,
  open_to_work: true,
  is_discoverable: false,
  resume_text: "Existing resume",
  data_consent_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  experiences: [],
  education: [],
  skills: [{ id: 1, skill: "Python", skill_normalized: "python", years: 5, verified: false, verified_source: null }],
  preferences: null,
  vault_answers: {},
}

async function setToken(page: import("@playwright/test").Page, orgId?: number) {
  await page.addInitScript((activeOrgId) => {
    window.localStorage.setItem("evalia_token", "test-token")
    if (activeOrgId !== undefined) window.localStorage.setItem("evalia_org_id", String(activeOrgId))
  }, orgId)
}

test("resume upload opens an editable review and saves the profile", async ({ page }) => {
  let saved = false
  await setToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  await page.route("**/api/me/profile", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(saved ? { ...profile, headline: "Imported Platform Engineer" } : profile) }))
  await page.route("**/api/me/resume/parse", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      resume_document_id: 3,
      char_count: 42,
      parsed_by: "heuristic",
      raw_text: "Avery Candidate\nPlatform engineer\nPython",
      parsed: {
        headline: "Platform Engineer",
        summary: "Builds platform services.",
        location: "Remote",
        phone: "",
        work_authorization: "",
        years_experience: 6,
        skills: [{ skill: "Python", years: 6 }],
        work_experiences: [],
        education: [],
      },
      warnings: ["Review the extracted fields."],
    }),
  }))
  await page.route("**/api/me/resume/import", async (route) => {
    saved = true
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...profile, headline: "Imported Platform Engineer" }) })
  })

  await page.goto("/profile")
  await expect(page.getByRole("button", { name: "Import resume" })).toBeVisible()
  const chooser = page.waitForEvent("filechooser")
  await page.getByRole("button", { name: "Import resume" }).click()
  await (await chooser).setFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from("Avery Candidate\nPlatform engineer\nPython") })

  await expect(page.getByRole("heading", { name: "Review imported resume" })).toBeVisible()
  await expect(page.getByLabel("HEADLINE")).toHaveValue("Platform Engineer")
  await page.getByLabel("HEADLINE").fill("Imported Platform Engineer")
  await page.getByRole("button", { name: "Save profile" }).click()
  await expect(page.getByText("Imported Platform Engineer").first()).toBeVisible()
})

test("posting criteria loads, edits weights, and saves", async ({ page }) => {
  await setToken(page, 4)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(recruiterActor) }))
  await page.route("**/api/orgs/4/postings/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: 1, org_id: 4, campaign_id: 2, title: "Platform Engineer", description: "", location: "Remote", employment_type: "FULL_TIME", remote_policy: "REMOTE", min_experience: null, max_experience: null, salary_min: null, salary_max: null, currency: "USD", required_skills: ["Python"], screening_questions: [], status: "PUBLISHED", auto_reject_enabled: false, created_at: "2026-09-30T00:00:00Z" }) }))
  await page.route("**/api/orgs/4/postings/1/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [], funnel: { by_stage: {} } }) }))
  await page.route("**/api/orgs/4/postings/1/criteria", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON()
      expect(body.competencies[0].weight).toBe(70)
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ posting_id: 1, ...body, rubric_version: "posting-v1", updated_at: "2026-09-30T00:00:00Z" }) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ posting_id: 1, competencies: [{ key: "technical_skills", label: "Technical skills", weight: 60, description: "" }, { key: "communication", label: "Communication", weight: 40, description: "" }], custom_questions: [], pass_threshold: 6, rubric_version: "posting-v1", updated_at: "" }) })
  })

  await page.goto("/org/postings/1")
  await page.getByRole("button", { name: "Evaluation criteria" }).click()
  await expect(page.getByRole("heading", { name: "Evaluation criteria" })).toBeVisible()
  await page.getByLabel("WEIGHT %").nth(0).fill("70")
  await page.getByLabel("WEIGHT %").nth(1).fill("30")
  await page.getByRole("button", { name: "Save criteria" }).click()
  await expect(page.getByText("100% total weight")).toBeVisible()
})
