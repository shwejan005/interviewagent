import { expect, test } from "@playwright/test"

const candidateActor = {
  user_id: 7,
  email: "candidate@example.com",
  full_name: "Candidate",
  is_platform_admin: false,
  email_verified_at: null,
  email_verification_required: true,
  active_org_id: null,
  active_role: "candidate",
  capabilities: [],
  memberships: [],
}

async function seedCandidateSession(page: import("@playwright/test").Page) {
  await page.addInitScript(() => window.localStorage.setItem("evalia_token", "candidate-token"))
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
}

test("signup gives a generic verification next step and preserves candidate intent", async ({ page }) => {
  let registrationBody: Record<string, unknown> | null = null
  await page.route("**/api/auth/register", async (route) => {
    registrationBody = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ message: "If an account can be created, next steps will be sent to that email address. If verification is disabled, you can sign in now.", verification_required: true }) })
  })

  await page.goto("/register?intent=candidate&next=%2Fjobs%2F1")
  await page.getByLabel("FULL NAME").fill("Candidate Example")
  await page.getByLabel("EMAIL").fill("candidate@example.com")
  await page.getByLabel("PASSWORD").fill("correct-horse-battery")
  await page.getByRole("button", { name: "Create free account" }).click()

  await expect(page.getByRole("status")).toContainText("If an account can be created")
  const verifyLink = page.getByRole("link", { name: "Check verification options" })
  await expect(verifyLink).toHaveAttribute("href", /verify-email\?email=candidate%40example\.com&next=%2Fjobs%2F1/)
  expect(registrationBody).toMatchObject({ email: "candidate@example.com", full_name: "Candidate Example" })
})

test("email verification consumes the link and offers the preserved login destination", async ({ page }) => {
  await page.route("**/api/auth/verify-email", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ token: "one-time-token" })
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: "Email verified. You can now sign in." }) })
  })

  await page.goto("/verify-email?token=one-time-token&next=%2Fjobs%2F1")
  await expect(page.getByRole("status")).toContainText("Email verified")
  await expect(page.getByRole("link", { name: "Continue to log in" })).toHaveAttribute("href", "/login?next=%2Fjobs%2F1")
})

test("password reset sends generic instructions and accepts a new password once", async ({ page }) => {
  let requestCount = 0
  await page.route("**/api/auth/password-reset/request", async (route) => {
    requestCount += 1
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ message: "If an eligible account exists, instructions will be sent to that email address." }) })
  })
  await page.goto("/password-reset")
  await page.getByLabel("EMAIL").fill("candidate@example.com")
  await page.getByRole("button", { name: "Send reset instructions" }).click()
  await expect(page.getByRole("status")).toContainText("If an eligible account exists")
  expect(requestCount).toBe(1)

  await page.route("**/api/auth/password-reset/confirm", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ token: "one-time-reset-token", new_password: "another-correct-horse-password" })
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: "Password updated. Sign in with your new password." }) })
  })
  await page.goto("/password-reset?token=one-time-reset-token")
  await page.getByLabel("NEW PASSWORD", { exact: true }).fill("another-correct-horse-password")
  await page.getByLabel("CONFIRM NEW PASSWORD").fill("another-correct-horse-password")
  await page.getByRole("button", { name: "Update password" }).click()
  await expect(page.getByRole("status")).toContainText("Password updated")
  await expect(page.getByRole("link", { name: "Continue to log in" })).toHaveAttribute("href", "/login")
})

test("notification inbox renders persisted updates and marks them read", async ({ page }) => {
  await seedCandidateSession(page)
  let unreadCount = 1
  let readAt: string | null = null
  const notification = {
    id: 61,
    org_id: 4,
    application_id: 55,
    notification_type: "AI_INTERVIEW_READY",
    title: "Your next interview step is ready",
    body: "Review the text interview details when you are ready.",
    href: "/ai-interview/55",
    metadata: {},
    created_at: "2026-10-01T09:00:00Z",
    get read_at() { return readAt },
  }
  await page.route("**/api/me/notifications**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ notifications: [{ ...notification, read_at: readAt }], unread_count: unreadCount, has_more: false }),
  }))
  await page.route("**/api/me/notifications/61/read", async (route) => {
    unreadCount = 0
    readAt = "2026-10-01T09:05:00Z"
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ notification_id: 61, read: true }) })
  })
  await page.route("**/api/me/applications/55/ai-interview", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      application_id: 55,
      status: "INTERVIEW_READY",
      phase: "TECHNICAL",
      rubric_version: "posting-v1",
      role_level: "MID",
      candidate_notice_version: "ai-interview-v1",
      consent_required: true,
      current_question: null,
      turns: [],
      message: "Your AI interview is ready.",
    }),
  }))

  await page.goto("/notifications")
  await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible()
  await expect(page.getByText("1 unread")).toBeVisible()
  await page.getByRole("button", { name: /Your next interview step is ready/ }).click()
  await expect(page).toHaveURL(/\/ai-interview\/55$/, { timeout: 30_000 })
  await expect(page.getByText("Your AI interview is ready.")).toBeVisible()
})
