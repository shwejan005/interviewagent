import { expect, test } from "@playwright/test"

const recruiterActor = {
  user_id: 8,
  email: "recruiter@example.com",
  full_name: "Recruiter",
  is_platform_admin: false,
  active_org_id: 4,
  active_role: "org_owner",
  capabilities: ["campaign:read_org", "campaign:create", "campaign:update", "posting:publish", "application:read"],
  memberships: [{ org_id: 4, org_name: "Acme", org_slug: "acme", role_name: "org_owner" }],
}

const campaignSeed = {
  id: 7,
  org_id: 4,
  name: "Platform Hiring",
  description: "Grow the platform team.",
  status: "ACTIVE" as "ACTIVE" | "CLOSED",
  department: "Engineering",
  hiring_manager: "Riley Manager",
  priority: "HIGH" as const,
  target_hires: 3 as number | null,
  target_close_date: "2026-12-31" as string | null,
  created_at: "2026-10-01T00:00:00Z",
  deleted_at: null as string | null,
  posting_count: 1,
  applicant_count: 2,
}

const postingSeed = {
  id: 11,
  org_id: 4,
  campaign_id: 7,
  title: "Backend Engineer",
  description: "Build dependable backend services.",
  location: "Remote",
  employment_type: "FULL_TIME",
  remote_policy: "REMOTE",
  min_experience: 3 as number | null,
  max_experience: 8 as number | null,
  salary_min: 120000 as number | null,
  salary_max: 180000 as number | null,
  currency: "USD",
  required_skills: ["Python", "PostgreSQL"],
  screening_questions: [{ key: "reliability_story", text: "Describe a reliability improvement.", required: true }],
  status: "PUBLISHED" as "DRAFT" | "PUBLISHED" | "CLOSED",
  auto_reject_enabled: false,
  created_at: "2026-10-01T00:00:00Z",
  deleted_at: null as string | null,
  applicant_count: 2,
}

async function useRecruiterSession(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("evalia_token", "recruiter-token")
    window.localStorage.setItem("evalia_org_id", "4")
  })
  await page.route("**/api/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(recruiterActor),
  }))
}

test("campaign card edits, closes, archives, and restores without losing its history", async ({ page }) => {
  await useRecruiterSession(page)
  let campaign = { ...campaignSeed }

  await page.route(/\/api\/orgs\/4\/campaigns\?include_archived=true$/, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ campaigns: [campaign] }),
  }))
  await page.route("**/api/orgs/4/campaigns/7/restore", async (route) => {
    expect(route.request().method()).toBe("POST")
    campaign = { ...campaign, deleted_at: null, status: "CLOSED" }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) })
  })
  await page.route("**/api/orgs/4/campaigns/7", async (route) => {
    if (route.request().method() === "DELETE") {
      campaign = { ...campaign, status: "CLOSED", deleted_at: "2026-10-01T12:00:00Z" }
      await route.fulfill({ status: 204 })
      return
    }
    if (route.request().method() === "PATCH") {
      const payload = route.request().postDataJSON()
      expect(payload).toMatchObject({ name: "Platform Hiring - Q4", status: "CLOSED" })
      campaign = { ...campaign, ...payload }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) })
  })

  await page.goto("/org")
  await page.getByRole("button", { name: "Edit campaign Platform Hiring" }).click()
  await expect(page.getByLabel("CAMPAIGN NAME")).toHaveValue("Platform Hiring")
  await page.getByLabel("CAMPAIGN NAME").fill("Platform Hiring - Q4")
  await page.getByLabel("CAMPAIGN STATUS").selectOption("CLOSED")
  await page.getByRole("button", { name: "Save changes" }).click()
  await page.getByRole("button", { name: "Closed (1)" }).click()
  await expect(page.getByText("Platform Hiring - Q4")).toBeVisible()
  await expect(page.getByText("CLOSED", { exact: true }).first()).toBeVisible()

  await page.getByRole("button", { name: "Archive campaign Platform Hiring - Q4" }).click()
  await expect(page.getByRole("heading", { name: "Archive Platform Hiring - Q4?" })).toBeVisible()
  await page.getByRole("button", { name: "Archive campaign", exact: true }).click()
  await expect(page.getByRole("button", { name: "Archived (1)" })).toBeVisible()
  await page.getByRole("button", { name: "Archived (1)" }).click()
  await expect(page.getByText("ARCHIVED", { exact: true }).first()).toBeVisible()
  await page.getByRole("button", { name: "Restore campaign Platform Hiring - Q4" }).click()
  await page.getByRole("button", { name: "Closed (1)" }).click()
  await expect(page.getByText("Platform Hiring - Q4")).toBeVisible()
  await expect(page.getByText("CLOSED", { exact: true }).first()).toBeVisible()
})

test("posting card edits fields and application questions, then archives and restores explicitly closed", async ({ page }) => {
  await useRecruiterSession(page)
  let campaign = { ...campaignSeed }
  let posting = { ...postingSeed }
  await page.route("**/api/orgs/4/campaigns/7", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) }))
  await page.route(/\/api\/orgs\/4\/postings\?campaign_id=7&include_archived=true$/, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ postings: [posting] }),
  }))
  await page.route("**/api/orgs/4/postings/11", async (route) => {
    const method = route.request().method()
    if (method === "PATCH") {
      const payload = route.request().postDataJSON()
      expect(payload).toMatchObject({
        title: "Senior Backend Engineer",
        min_experience: null,
        screening_questions: [{ key: "reliability_story", text: "Tell us about reliability work.", required: true }],
      })
      posting = { ...posting, ...payload }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
      return
    }
    if (method === "DELETE") {
      posting = { ...posting, status: "CLOSED", deleted_at: "2026-10-01T12:00:00Z" }
      await route.fulfill({ status: 204 })
      return
    }
    if (method === "POST") {
      const payload = route.request().postDataJSON()
      expect(payload).toMatchObject({ status: "PUBLISHED" })
      posting = { ...posting, status: "PUBLISHED" }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
  })
  await page.route("**/api/orgs/4/postings/11/restore", async (route) => {
    expect(route.request().method()).toBe("POST")
    posting = { ...posting, deleted_at: null, status: "CLOSED" }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
  })
  await page.route("**/api/orgs/4/postings/11/status", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ status: "PUBLISHED" })
    posting = { ...posting, status: "PUBLISHED" }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
  })

  await page.goto("/org/campaigns/7")
  await page.getByRole("button", { name: "Edit role Backend Engineer" }).click()
  await page.getByLabel("ROLE TITLE").fill("Senior Backend Engineer")
  await page.getByLabel("MIN EXP (YRS)").fill("")
  await page.getByLabel("QUESTION 1", { exact: true }).fill("Tell us about reliability work.")
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect(page.getByRole("link", { name: "Senior Backend Engineer" })).toBeVisible()

  await page.getByRole("button", { name: "Archive role Senior Backend Engineer" }).click()
  await expect(page.getByRole("heading", { name: "Archive Senior Backend Engineer?" })).toBeVisible()
  await page.getByRole("button", { name: "Archive role", exact: true }).click()
  await page.getByRole("button", { name: "Archived (1)" }).click()
  await expect(page.getByText("ARCHIVED", { exact: true }).first()).toBeVisible()
  await page.getByRole("button", { name: "Restore role Senior Backend Engineer" }).click()
  await page.getByRole("button", { name: "Closed (1)" }).click()
  await expect(page.getByRole("button", { name: "Reopen role" })).toBeVisible()
  await page.getByRole("button", { name: "Reopen role" }).click()
  await page.getByRole("button", { name: /Open roles/ }).click()
  await expect(page.getByText("PUBLISHED", { exact: true })).toBeVisible()
})

test("closed campaigns keep roles editable but require campaign reopen before publishing", async ({ page }) => {
  await useRecruiterSession(page)
  let campaign = { ...campaignSeed, status: "CLOSED" as const }
  let posting = { ...postingSeed, status: "CLOSED" as const }

  await page.route("**/api/orgs/4/campaigns/7", async (route) => {
    if (route.request().method() === "PATCH") {
      const payload = route.request().postDataJSON()
      expect(payload).toMatchObject({ status: "ACTIVE" })
      campaign = { ...campaign, ...payload }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(campaign) })
  })
  await page.route(/\/api\/orgs\/4\/postings\?campaign_id=7&include_archived=true$/, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ postings: [posting] }),
  }))
  await page.route("**/api/orgs/4/postings/11", async (route) => {
    if (route.request().method() === "PATCH") {
      const payload = route.request().postDataJSON()
      expect(payload).toMatchObject({ description: "Updated description while closed." })
      posting = { ...posting, ...payload }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) })
  })

  await page.goto("/org/campaigns/7")
  await expect(page.getByRole("button", { name: "Add a role" })).toBeDisabled()
  await page.getByRole("button", { name: "Closed (1)" }).click()
  await page.getByRole("button", { name: "Edit role Backend Engineer" }).click()
  await page.getByLabel("DESCRIPTION", { exact: true }).fill("Updated description while closed.")
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect(page.getByRole("button", { name: "Reopen role" })).toBeDisabled()

  await page.getByRole("button", { name: "Reopen campaign" }).click()
  await expect(page.getByRole("button", { name: "Reopen role" })).toBeEnabled()
  await expect(page.getByText("CLOSED", { exact: true }).first()).toBeVisible()
})
