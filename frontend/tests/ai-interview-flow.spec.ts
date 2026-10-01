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
  capabilities: ["campaign:read_org", "campaign:update", "application:read"],
  memberships: [{ org_id: 4, org_name: "Acme", org_slug: "acme", role_name: "org_owner" }],
}

const posting = {
  id: 1,
  org_id: 4,
  campaign_id: 2,
  title: "Platform Engineer",
  description: "Build reliable platform services.",
  location: "Remote",
  employment_type: "FULL_TIME",
  remote_policy: "REMOTE",
  min_experience: 3,
  max_experience: 8,
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
  id: 55,
  org_id: 4,
  posting_id: 1,
  candidate_user_id: 7,
  status: "IN_PROGRESS",
  current_stage: "AI_INTERVIEW",
  source: "DIRECT",
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  withdrawn_at: null,
  posting_title: "Platform Engineer",
  org_name: "Acme",
  location: "Remote",
  remote_policy: "REMOTE",
  ai_interview_status: "INTERVIEW_READY",
  ai_interview_phase: "TECHNICAL",
  candidate_name: "Candidate",
  candidate_email: "candidate@example.com",
  profile_snapshot: {},
}

const firstQuestion = {
  id: 901,
  sequence_no: 1,
  phase: "TECHNICAL" as const,
  question_type: "CORE" as const,
  competency_key: "python",
  difficulty: 2,
  question_text: "How would you make a Python API resilient to a database outage?",
  answer_text: null,
  state: "ASKED" as const,
}

const nextQuestion = {
  ...firstQuestion,
  id: 902,
  sequence_no: 2,
  question_text: "What trade-off would you consider when retrying failed requests?",
}

async function setCandidateToken(page: import("@playwright/test").Page) {
  await page.addInitScript(() => window.localStorage.setItem("evalia_token", "candidate-token"))
}

async function setRecruiterToken(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("evalia_token", "recruiter-token")
    window.localStorage.setItem("evalia_org_id", "4")
  })
}

test("application submit queues screening and candidate can resume a persisted AI interview", async ({ page }) => {
  await setCandidateToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  await page.route("**/api/jobs/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) }))
  await page.route("**/api/jobs/1/application-form", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ posting_id: 1, title: posting.title, questions: [], profile_complete: true, missing_profile_fields: [], unanswered_count: 0 }),
  }))
  await page.route("**/api/jobs/1/apply", async (route) => {
    expect(route.request().method()).toBe("POST")
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ application_id: 55, status: "SCREENING_QUEUED", screening_status: "QUEUED" }) })
  })

  await page.goto("/jobs/1")
  await page.getByRole("button", { name: "Submit application" }).click()
  await expect(page.getByText("APPLICATION SUBMITTED · SCREENING QUEUED")).toBeVisible()
  await expect(page.getByText(/screened automatically/i)).toBeVisible()

  await page.route("**/api/me/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], limit: 50, offset: 0 }) }))
  await page.route("**/api/me/applications/55", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application, timeline: [] }) }))
  await page.goto("/applications")
  await page.getByRole("button", { name: /Platform Engineer/ }).click()
  await page.getByRole("link", { name: "Start AI interview" }).click()

  let started = false
  let answerSubmitted = false
  await page.route("**/api/me/applications/55/ai-interview", (route) => {
    const body = started
      ? {
          application_id: 55,
          status: answerSubmitted ? "INTERVIEW_IN_PROGRESS" : "INTERVIEW_IN_PROGRESS",
          phase: "TECHNICAL",
          rubric_version: "posting-v1",
          role_level: "MID",
          candidate_notice_version: "ai-interview-v1",
          consent_required: false,
          current_question: answerSubmitted ? nextQuestion : firstQuestion,
          turns: answerSubmitted ? [{ ...firstQuestion, answer_text: "A saved answer." }, nextQuestion] : [firstQuestion],
          message: "Your AI interview is in progress.",
        }
      : {
          application_id: 55,
          status: "INTERVIEW_READY",
          phase: "TECHNICAL",
          rubric_version: "posting-v1",
          role_level: "MID",
          candidate_notice_version: "ai-interview-v1",
          consent_required: true,
          current_question: firstQuestion,
          turns: [firstQuestion],
          message: "Your AI interview is ready.",
        }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
  })
  await page.route("**/api/me/applications/55/ai-interview/start", async (route) => {
    const request = route.request().postDataJSON()
    expect(request).toMatchObject({ accepted: true, notice_version: "ai-interview-v1", modality: "TEXT" })
    started = true
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      application_id: 55,
      status: "INTERVIEW_IN_PROGRESS",
      phase: "TECHNICAL",
      rubric_version: "posting-v1",
      role_level: "MID",
      candidate_notice_version: "ai-interview-v1",
      consent_required: false,
      current_question: firstQuestion,
      turns: [firstQuestion],
      message: "Your interview has started.",
    }) })
  })
  await page.route("**/api/me/applications/55/ai-interview/answers", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ turn_id: firstQuestion.id })
    answerSubmitted = true
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "ANSWER_PROCESSING", job_id: 90 }) })
  })

  await page.goto("/ai-interview/55")
  await expect(page.getByText("This is an AI-led text interview")).toBeVisible()
  await page.getByRole("checkbox").check()
  await page.getByRole("button", { name: "Start interview" }).click()
  await expect(page.getByRole("heading", { name: firstQuestion.question_text })).toBeVisible()
  await page.getByLabel("YOUR ANSWER").fill("I would use bounded retries and a circuit breaker.")
  await page.getByRole("button", { name: "Submit answer" }).click()
  await expect(page.getByRole("heading", { name: nextQuestion.question_text })).toBeVisible()
})

test("recruiter applicant pipeline no longer has a manual screen action", async ({ page }) => {
  await setRecruiterToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(recruiterActor) }))
  await page.route("**/api/orgs/4/postings/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) }))
  await page.route("**/api/orgs/4/postings/1/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], funnel: { by_stage: { AI_INTERVIEW: 1 } } }) }))
  await page.route("**/api/orgs/4/applications/55", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application, answers: [], timeline: [] }) }))
  await page.route("**/api/orgs/4/applications/55/ai-interview", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application_id: 55, status: "INTERVIEW_READY", phase: "TECHNICAL", rubric_version: "posting-v1", role_level: "MID", screening_result: { decision: "PASS", score: 8 }, turns: [] }) }))
  await page.route("**/api/orgs/4/applications/55/report", (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No report yet" }) }))

  await page.goto("/org/postings/1")
  await expect(page.getByRole("button", { name: "View" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Screen" })).toHaveCount(0)
  await page.getByRole("button", { name: "View" }).click()
  await expect(page.getByText("AUTOMATIC SCREENING & AI INTERVIEW")).toBeVisible()
  await expect(page.getByRole("dialog").getByText("INTERVIEW READY")).toBeVisible()
})
