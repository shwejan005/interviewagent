import { expect, test } from "@playwright/test"

const actor = {
  user_id: 7,
  email: "candidate@example.com",
  full_name: "Candidate",
  is_platform_admin: false,
  active_org_id: null,
  active_role: "candidate",
  capabilities: ["evaluation:read"],
  memberships: [],
}

const problem = {
  id: 1,
  slug: "two-sum",
  title: "Two Sum",
  prompt: "Return the indices of two values that add to the target.",
  difficulty: "EASY",
  estimated_minutes: 25,
  topic_name: "Arrays",
  topic_slug: "arrays",
  expected_concepts: ["arrays", "hashing"],
  constraints: ["2 <= nums.length"],
  hint: "Use a lookup map.",
  starter_code: { python: "class Solution:\n    def two_sum(self, nums, target):\n        pass\n" },
  available_languages: ["python"],
  test_cases: [{ id: 1, title: "Basic pair", input: { nums: [2, 7], target: 9 }, expected_output: "[0,1]", explanation: "Basic case", is_hidden: false, position: 1 }],
}

async function mockPrepApi(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(actor) }))
  await page.route("**/api/prep/catalog", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ topics: [{ id: 1, slug: "arrays", name: "Arrays", description: "", difficulty: "FOUNDATION" }], problems: [problem] }) }))
  await page.route("**/api/prep/me/dashboard", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ total_problems: 1, solved_problems: 0, solved_problem_ids: [], attempts: 0, completion_percent: 0, xp: 0, streak_days: 0, by_topic: [{ slug: "arrays", name: "Arrays", total: 1, solved: 0 }], recent_submissions: [], goal: null }) }))
  await page.route("**/api/prep/problems/1/submissions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ submissions: [] }) }))
  await page.addInitScript(() => window.localStorage.setItem("evalia_token", "test-token"))
}

test("prep homepage opens a problem and survives refresh", async ({ page }) => {
  await mockPrepApi(page)
  await page.goto("/prep")

  await expect(page.getByRole("heading", { name: "Choose your next problem" })).toBeVisible()
  const problemLink = page.locator("main").getByRole("link", { name: /Two Sum/ })
  await expect(problemLink).toHaveAttribute("href", "/prep?problem=1")
  await problemLink.click()
  await expect(page).toHaveURL(/\/prep\?problem=1$/)
  await expect(page.getByLabel("Problem description").getByRole("heading", { name: "Two Sum" })).toBeVisible()

  await page.reload()
  await expect(page.getByLabel("Problem description").getByRole("heading", { name: "Two Sum" })).toBeVisible()
  await expect(page.getByText("Problem set", { exact: true }).first()).toBeVisible()
})

test("prep navigation keeps the shared sidebar on roadmap and insights", async ({ page }) => {
  await mockPrepApi(page)
  await page.route("**/api/prep/goals", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ goal: null }) }))
  const documentRequests: string[] = []
  let catalogRequests = 0
  page.on("request", (request) => {
    if (request.isNavigationRequest()) documentRequests.push(request.url())
    if (request.url().includes("/api/prep/catalog")) catalogRequests += 1
  })
  await page.goto("/prep")

  const roadmapLink = page.locator('[data-sidebar="sidebar"] a[href="/prep/roadmap"]')
  await expect(roadmapLink).toHaveCount(1)
  await roadmapLink.click()
  await expect(page).toHaveURL(/\/prep\/roadmap$/, { timeout: 15_000 })
  await expect(page.getByRole("link", { name: "Problem set" })).toBeVisible()

  await page.getByRole("link", { name: "Insights", exact: true }).click()
  await expect(page).toHaveURL(/\/prep\/dashboard$/, { timeout: 15_000 })
  await expect(page.getByRole("link", { name: "Roadmap", exact: true })).toBeVisible()
  expect(documentRequests).toHaveLength(1)
  expect(catalogRequests).toBe(1)
})
