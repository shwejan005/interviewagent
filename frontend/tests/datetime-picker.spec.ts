import { expect, test } from "@playwright/test"

const actor = {
  user_id: 8,
  email: "recruiter@example.com",
  full_name: "Recruiter",
  is_platform_admin: false,
  active_org_id: 4,
  active_role: "org_owner",
  capabilities: ["campaign:read_org", "campaign:update", "application:read"],
  memberships: [{ org_id: 4, org_name: "Acme", org_slug: "acme", role_name: "org_owner" }],
}

const posting = {
  id: 1,
  org_id: 4,
  campaign_id: 2,
  title: "Platform Engineer",
  description: "",
  location: "Remote",
  employment_type: "FULL_TIME",
  remote_policy: "REMOTE",
  min_experience: null,
  max_experience: null,
  salary_min: null,
  salary_max: null,
  currency: "USD",
  required_skills: ["Python"],
  screening_questions: [],
  status: "PUBLISHED",
  auto_reject_enabled: false,
  created_at: "2026-09-30T00:00:00Z",
}

const application = {
  id: 1,
  org_id: 4,
  posting_id: 1,
  candidate_user_id: 9,
  status: "ACTIVE",
  current_stage: "INTERVIEW",
  source: "DIRECT",
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  candidate_name: "Candidate",
  candidate_email: "candidate@example.com",
  profile_snapshot: {},
}

test("schedule interview uses the custom date and time picker", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("evalia_token", "test-token")
    window.localStorage.setItem("evalia_org_id", "4")
  })
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(actor) }))
  await page.route("**/api/orgs/4/postings/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) }))
  await page.route("**/api/orgs/4/postings/1/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], funnel: { by_stage: { INTERVIEW: 1 } } }) }))
  await page.route("**/api/orgs/4/applications/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application, answers: [], timeline: [] }) }))
  await page.route("**/api/orgs/4/applications/1/report", (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No report yet" }) }))
  let schedulePayload: Record<string, unknown> | null = null
  await page.route("**/api/orgs/4/applications/1/interviews", async (route) => {
    schedulePayload = route.request().postDataJSON()
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: 4, status: "SCHEDULED" }) })
  })

  await page.goto("/org/postings/1")
  await page.getByRole("button", { name: "View" }).click()
  await expect(page.getByText("SCHEDULE HUMAN INTERVIEW", { exact: true })).toBeVisible()
  await expect(page.locator('input[type="datetime-local"]')).toHaveCount(0)

  await page.getByRole("button", { name: "START", exact: true }).click()
  const startPicker = page.getByRole("dialog", { name: "START picker" })
  await expect(startPicker).toBeVisible()
  await expect(page.getByRole("dialog", { name: /picker$/ })).toHaveCount(1)
  await expect(startPicker.getByRole("button", { name: "Set AM" })).toBeVisible()
  await expect(startPicker.getByRole("button", { name: "Set PM" })).toBeVisible()
  await expect(startPicker.getByRole("button", { name: "Today" })).toBeVisible()
  expect((await startPicker.getByRole("button", { name: "Set AM" }).boundingBox())?.width).toBeGreaterThanOrEqual(56)
  await expect(startPicker.getByRole("button", { name: "Set AM" })).toHaveCSS("background-color", "rgb(249, 115, 22)")
  await expect(startPicker.getByRole("button", { name: "Done" })).toHaveCSS("background-color", "rgb(249, 115, 22)")

  const hour = startPicker.getByRole("spinbutton", { name: "Hour" })
  const minute = startPicker.getByRole("spinbutton", { name: "Minute" })
  await startPicker.getByRole("button", { name: "Increase hour" }).click()
  await expect(hour).toHaveValue("10")
  await startPicker.getByRole("button", { name: "Increase hour" }).click()
  await startPicker.getByRole("button", { name: "Increase hour" }).click()
  await expect(hour).toHaveValue("12")
  await expect(startPicker.getByRole("button", { name: "Set PM" })).toHaveAttribute("aria-pressed", "true")
  await startPicker.getByRole("button", { name: "Decrease hour" }).click()
  await expect(hour).toHaveValue("11")
  await expect(startPicker.getByRole("button", { name: "Set AM" })).toHaveAttribute("aria-pressed", "true")
  await startPicker.getByRole("button", { name: "Decrease minute" }).click()
  await expect(minute).toHaveValue("55")
  await expect(hour).toHaveValue("10")
  await startPicker.getByRole("button", { name: "Increase minute" }).click()
  await expect(minute).toHaveValue("00")
  await expect(hour).toHaveValue("11")

  await startPicker.getByRole("button", { name: "Today" }).click()
  await expect(page.getByRole("button", { name: "START", exact: true })).toContainText("11:00 AM")
  await startPicker.getByRole("button", { name: "Done" }).click()

  await page.getByRole("button", { name: "END", exact: true }).click()
  const endPicker = page.getByRole("dialog", { name: "END picker" })
  await expect(endPicker).toBeVisible()
  await expect(page.getByRole("dialog", { name: /picker$/ })).toHaveCount(1)
  await endPicker.getByRole("button", { name: "Today" }).click()
  await endPicker.getByRole("button", { name: "Done" }).click()
  await page.getByRole("button", { name: "Schedule interview" }).click()

  await expect.poll(() => schedulePayload).not.toBeNull()
  const submittedPayload = schedulePayload as { scheduled_start?: unknown; scheduled_end?: unknown } | null
  expect(submittedPayload?.scheduled_start).toEqual(expect.any(String))
  expect(submittedPayload?.scheduled_end).toEqual(expect.any(String))
})

test("date and time picker stacks cleanly on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.addInitScript(() => {
    window.localStorage.setItem("evalia_token", "test-token")
    window.localStorage.setItem("evalia_org_id", "4")
  })
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(actor) }))
  await page.route("**/api/orgs/4/postings/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) }))
  await page.route("**/api/orgs/4/postings/1/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], funnel: { by_stage: { INTERVIEW: 1 } } }) }))
  await page.route("**/api/orgs/4/applications/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application, answers: [], timeline: [] }) }))
  await page.route("**/api/orgs/4/applications/1/report", (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No report yet" }) }))

  await page.goto("/org/postings/1")
  await page.getByRole("button", { name: "View" }).click()
  await page.getByRole("button", { name: "START", exact: true }).click()

  const picker = page.getByRole("dialog", { name: "START picker" })
  await expect(picker).toBeVisible()
  await expect(picker).toHaveCSS("flex-direction", "column")
  const pickerBox = await picker.boundingBox()
  expect(pickerBox).not.toBeNull()
  expect(pickerBox?.x).toBeGreaterThanOrEqual(0)
  expect((pickerBox?.x || 0) + (pickerBox?.width || 0)).toBeLessThanOrEqual(390)
})
