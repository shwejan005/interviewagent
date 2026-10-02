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
  await page.route("**/api/me/notifications?limit=6", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ notifications: [], unread_count: 0 }) }))
}

async function setRecruiterToken(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("evalia_token", "recruiter-token")
    window.localStorage.setItem("evalia_org_id", "4")
  })
  await page.route("**/api/me/notifications?limit=6", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ notifications: [], unread_count: 0 }) }))
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
  let submittedAnswer = ""
  await page.route("**/api/me/applications/55/ai-interview", (route) => {
    const body = started
      ? {
          application_id: 55,
          status: answerSubmitted ? "INTERVIEW_IN_PROGRESS" : "INTERVIEW_IN_PROGRESS",
          modality: "VOICE",
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
          modality: "TEXT",
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
    expect(request).toMatchObject({ accepted: true, notice_version: "ai-interview-v1", modality: "VOICE" })
    started = true
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      application_id: 55,
      status: "INTERVIEW_IN_PROGRESS",
      modality: "VOICE",
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
    const body = route.request().postDataJSON() as { turn_id: number; answer: string; source: string }
    expect(body).toMatchObject({ turn_id: firstQuestion.id, source: "VOICE" })
    submittedAnswer = body.answer
    answerSubmitted = true
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "ANSWER_PROCESSING", job_id: 90 }) })
  })

  await page.addInitScript(() => {
    type MockResult = { 0: { transcript: string }; isFinal: boolean; length: number };
    type MockEvent = { resultIndex: number; results: ArrayLike<MockResult> };
    class MockSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = "en-US";
      onresult: ((event: MockEvent) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        window.setTimeout(() => this.onresult?.({
          resultIndex: 0,
          results: [{ 0: { transcript: "I would use bounded retries and a circuit breaker." }, isFinal: true, length: 1 }],
        }), 0);
      }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
    }
    const speechWindow = window as Window & { SpeechRecognition?: unknown };
    speechWindow.SpeechRecognition = MockSpeechRecognition;
  })
  await page.goto("/ai-interview/55")
  await expect(page.getByText("Your AI interviewer is ready")).toBeVisible()
  await page.getByRole("checkbox").check()
  await page.getByRole("button", { name: "Join AI interview" }).click()
  await expect(page.getByRole("heading", { name: firstQuestion.question_text })).toBeVisible()
  await page.getByRole("button", { name: "Start speaking" }).click()
  await expect(page.getByLabel("Live transcript captions")).toContainText("I would use bounded retries and a circuit breaker.")
  await page.getByRole("button", { name: "Finish speaking" }).click()
  await page.getByLabel("REVIEW AND CORRECT TRANSCRIPT").fill("I would use bounded retries, a circuit breaker, and observe recovery metrics.")
  await page.getByRole("button", { name: "Submit voice answer" }).click()
  await expect(page.getByRole("heading", { name: nextQuestion.question_text })).toBeVisible()
  expect(submittedAnswer).toBe("I would use bounded retries, a circuit breaker, and observe recovery metrics.")
})

test("candidate can join the automatically prepared AI interview from the unified agenda", async ({ page }) => {
  await setCandidateToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  await page.route("**/api/me/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], limit: 50, offset: 0 }) }))
  await page.route("**/api/me/interviews", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ interviews: [{
      id: "ai-55",
      application_id: 55,
      kind: "AI",
      title: "AI interview",
      posting_title: posting.title,
      org_name: "Acme",
      status: "INTERVIEW_READY",
      phase: "TECHNICAL",
      modality: "TEXT",
      join_href: "/ai-interview/55",
      can_join: true,
      scheduled_start: null,
      scheduled_end: null,
      timezone: "",
      meeting_url: "",
    }] }),
  }))
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
      current_question: firstQuestion,
      turns: [firstQuestion],
      message: "Your AI interview is ready.",
    }),
  }))

  await page.goto("/interviews")
  await expect(page.getByRole("heading", { name: "Your interview agenda" })).toBeVisible()
  await expect(page.getByText("AI-LED")).toBeVisible()
  await page.getByRole("link", { name: "Join AI interview" }).click()
  await expect(page).toHaveURL(/\/ai-interview\/55$/)
  await expect(page.getByText("Your AI interviewer is ready")).toBeVisible()
})

test("candidate can switch an active voice interview to the text accommodation", async ({ page }) => {
  await setCandidateToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  let textMode = false
  await page.route("**/api/me/applications/55/ai-interview", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      application_id: 55,
      status: "INTERVIEW_IN_PROGRESS",
      modality: textMode ? "TEXT" : "VOICE",
      phase: "TECHNICAL",
      rubric_version: "posting-v1",
      role_level: "MID",
      candidate_notice_version: "ai-interview-v1",
      consent_required: false,
      current_question: firstQuestion,
      turns: [firstQuestion],
      message: "Your AI interview is in progress.",
    }),
  }))
  await page.route("**/api/me/applications/55/ai-interview/text-accommodation", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ notice_version: "ai-interview-v1" })
    textMode = true
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application_id: 55, modality: "TEXT", duplicate: false }) })
  })
  await page.route("**/api/me/applications/55/ai-interview/draft", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ turn_id: firstQuestion.id, saved: true, draft_answer_text: "", draft_updated_at: new Date().toISOString() }),
  }))

  await page.goto("/ai-interview/55")
  await expect(page.getByLabel("Live transcript captions")).toBeVisible()
  await page.getByRole("button", { name: "Switch to text accommodation" }).click()

  await expect(page.getByLabel("YOUR ANSWER (TEXT ACCOMMODATION)")).toBeVisible()
  await expect(page.getByText("Text accommodation selected")).toBeVisible()
})

test("unsubmitted interview answer draft autosaves and restores after refresh", async ({ page }) => {
  await setCandidateToken(page)
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  await page.route("**/api/me/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [application], limit: 50, offset: 0 }) }))

  let serverDraft = ""
  let draftUpdatedAt: string | null = null
  let answerSubmitted = false
  await page.route("**/api/me/applications/55/ai-interview", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(answerSubmitted ? {
      application_id: 55,
      status: "ANSWER_PROCESSING",
      modality: "TEXT",
      phase: "TECHNICAL",
      rubric_version: "posting-v1",
      role_level: "MID",
      candidate_notice_version: "ai-interview-v1",
      consent_required: false,
      current_question: null,
      turns: [],
      message: "Your answer is saved and being evaluated.",
    } : {
      application_id: 55,
      status: "INTERVIEW_IN_PROGRESS",
      modality: "TEXT",
      phase: "TECHNICAL",
      rubric_version: "posting-v1",
      role_level: "MID",
      candidate_notice_version: "ai-interview-v1",
      consent_required: false,
      current_question: { ...firstQuestion, draft_answer_text: serverDraft, draft_updated_at: draftUpdatedAt },
      turns: [{ ...firstQuestion, draft_answer_text: serverDraft, draft_updated_at: draftUpdatedAt }],
      message: "Your AI interview is in progress.",
    }),
  }))
  await page.route("**/api/me/applications/55/ai-interview/draft", async (route) => {
    expect(route.request().method()).toBe("PUT")
    const body = route.request().postDataJSON() as { turn_id: number; draft_answer_text: string }
    expect(body.turn_id).toBe(firstQuestion.id)
    serverDraft = body.draft_answer_text
    draftUpdatedAt = "2026-10-01T09:10:00Z"
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ turn_id: firstQuestion.id, saved: true, draft_answer_text: serverDraft, draft_updated_at: draftUpdatedAt }) })
  })
  await page.route("**/api/me/applications/55/ai-interview/answers", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ turn_id: firstQuestion.id, answer: serverDraft })
    answerSubmitted = true
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "ANSWER_PROCESSING", job_id: 91 }) })
  })

  await page.goto("/ai-interview/55")
  const answerText = "I would use bounded retries, observability, and a circuit breaker."
  await page.getByLabel("YOUR ANSWER").fill(answerText)
  await expect.poll(() => serverDraft).toBe(answerText)
  await expect(page.getByRole("status")).toContainText("Draft saved. You can return later.")

  await page.evaluate(() => window.localStorage.removeItem("evalia:ai-draft:7:55:901"))
  await page.reload()
  await expect(page.getByLabel("YOUR ANSWER")).toHaveValue(answerText)
  await page.getByRole("button", { name: "Save and return later" }).click()
  await expect(page).toHaveURL(/\/applications$/)
  await page.goto("/ai-interview/55")
  await expect(page.getByLabel("YOUR ANSWER")).toHaveValue(answerText)
  await page.getByRole("button", { name: "Submit answer" }).click()
  await expect(page.getByText("Your answer is safely saved.")).toBeVisible()
  expect(await page.evaluate(() => window.localStorage.getItem("evalia:ai-draft:7:55:901"))).toBeNull()
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

test("recruiter reviews the evidence fit nudge and confirms promotion", async ({ page }) => {
  await setRecruiterToken(page)
  const reviewApplication = { ...application, current_stage: "PENDING_REVIEW", ai_interview_status: "REPORT_READY" }
  let promoted = false
  let scheduledStart: string | null = null
  let scheduledEnd: string | null = null
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(recruiterActor) }))
  await page.route("**/api/orgs/4/postings/1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(posting) }))
  await page.route("**/api/orgs/4/postings/1/applications", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ applications: [{ ...reviewApplication, current_stage: promoted ? "TECHNICAL" : "PENDING_REVIEW" }], funnel: { by_stage: { PENDING_REVIEW: 1 } } }) }))
  await page.route("**/api/orgs/4/applications/55", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application: { ...reviewApplication, current_stage: promoted ? "TECHNICAL" : "PENDING_REVIEW" }, answers: [], timeline: [] }) }))
  await page.route("**/api/orgs/4/applications/55/ai-interview", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application_id: 55, status: "REPORT_READY", phase: "COMPLETE", rubric_version: "posting-v1", role_level: "MID", screening_result: { decision: "PASS", score: 8 }, turns: [] }) }))
  await page.route("**/api/orgs/4/applications/55/report", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      application_id: 55,
      evaluation_id: 9,
      posting_id: 1,
      competency_scores: [{ key: "python", label: "Python", weight: 100, score: 8, evidence: "Turn 1: grounded example." }],
      overall_weighted_score: 8,
      recommendation: "HUMAN_REVIEW_REQUIRED",
      rubric_version: "posting-v1",
      generated_at: "2026-10-02T10:00:00Z",
      interview_details: {
        fit_nudge: { band: "LIKELY_FIT", suggested_action: "PROMOTE", score_threshold: 6, evidence_coverage_percent: 100, summary: "Evidence leans toward likely fit.", calibration: "UNVALIDATED_ADVISORY" },
        requirements_coverage: [{ key: "python", label: "Python", kind: "COMPETENCY", status: "DEMONSTRATED", score: 8, weight: 100, evidence: "Turn 1 supports this skill." }],
        resume_claims: [{ claim: "Python", status: "CONFIRMED_IN_INTERVIEW", source: "RESUME", resume_evidence: "Python experience", interview_evidence: "Turn 1 supports this claim." }],
        interview: { turn_count: 1, role_level: "MID", turns: [] },
      },
    }),
  }))
  await page.route("**/api/orgs/4/applications/55/decision", async (route) => {
    const body = route.request().postDataJSON()
    expect(body).toMatchObject({ action: "PROMOTE", target_stage: "TECHNICAL", timezone: expect.any(String) })
    scheduledStart = body.scheduled_start
    scheduledEnd = body.scheduled_end
    expect(scheduledStart).toBeTruthy()
    expect(scheduledEnd).toBeTruthy()
    promoted = true
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ application_id: 55, from_stage: "PENDING_REVIEW", to_stage: "TECHNICAL", action: "PROMOTE" }) })
  })

  await page.goto("/org/postings/1")
  await page.getByRole("button", { name: "View" }).click()
  await expect(page.getByText("LIKELY FIT", { exact: true })).toBeVisible()
  await expect(page.getByText("JOB REQUIREMENTS COVERAGE")).toBeVisible()

  const now = new Date()
  const future = new Date(now)
  future.setDate(future.getDate() + 2)
  const futureDateLabel = future.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })
  const startPickerTrigger = page.getByLabel("NEXT-ROUND START")
  await startPickerTrigger.click()
  const startPicker = page.getByRole("dialog", { name: "NEXT-ROUND START picker" })
  if (future.getMonth() !== now.getMonth() || future.getFullYear() !== now.getFullYear()) {
    await startPicker.getByRole("button", { name: "Next month" }).click()
  }
  await startPicker.getByRole("button", { name: futureDateLabel }).click()
  await startPicker.getByRole("button", { name: "Done" }).click()

  await page.getByLabel("NEXT-ROUND END").click()
  const endPicker = page.getByRole("dialog", { name: "NEXT-ROUND END picker" })
  await endPicker.getByRole("button", { name: futureDateLabel }).click()
  await endPicker.getByRole("button", { name: "Increase hour" }).click()
  await endPicker.getByRole("button", { name: "Done" }).click()

  await page.getByRole("button", { name: "Promote and schedule technical round" }).click()
  await expect(page.getByText("Candidate promoted to the next round.")).toBeVisible()
  expect(promoted).toBe(true)
  expect(Date.parse(scheduledEnd!)).toBeGreaterThan(Date.parse(scheduledStart!))
})

test("recruiter can browse the interview team and invite an interviewer", async ({ page }) => {
  await setRecruiterToken(page)
  const teamActor = { ...recruiterActor, capabilities: [...recruiterActor.capabilities, "interview:schedule", "org:member:invite"] }
  let invitedEmail = ""
  let savedProfile: Record<string, unknown> | null = null
  let teamLoadCount = 0
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(teamActor) }))
  await page.route("**/api/orgs/4/team", (route) => {
    teamLoadCount += 1
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ members: [{ id: 1, user_id: 8, full_name: "Recruiter", email: "recruiter@example.com", role_name: "org_owner", status: "ACTIVE" }] }),
    })
  })
  await page.route("**/api/orgs/4/invitations", async (route) => {
    if (route.request().method() === "POST") {
      invitedEmail = route.request().postDataJSON().email
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ email_delivery: "not_configured" }) })
    } else {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ invitations: [] }) })
    }
  })
  await page.route("**/api/orgs/4/members/8/interview-profile", async (route) => {
    savedProfile = route.request().postDataJSON()
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ member: { user_id: 8 } }) })
  })

  await page.goto("/org/team")
  await expect(page.getByRole("heading", { name: "Interview team" })).toBeVisible()
  await expect(page.getByText("recruiter@example.com", { exact: true }).last()).toBeVisible()
  await page.getByLabel("WORK EMAIL").fill("interviewer@example.com")
  await page.getByRole("button", { name: "Invite" }).click()
  await expect.poll(() => invitedEmail).toBe("interviewer@example.com")
  await expect.poll(() => teamLoadCount).toBeGreaterThan(1)
  await page.getByLabel("JOB TITLE").fill("Platform Interviewer")
  await page.getByLabel("TIMEZONE").fill("Asia/Kolkata")
  await page.getByLabel("INTERVIEW SKILLS").fill("Python, Distributed systems")
  await page.getByLabel("MAX INTERVIEWS PER WEEK").fill("3")
  await page.getByLabel("Available for interview assignments").uncheck()
  await page.getByRole("button", { name: "Save interview profile" }).click()
  await expect.poll(() => savedProfile).toMatchObject({
    job_title: "Platform Interviewer",
    interview_skills: ["Python", "Distributed systems"],
    timezone: "Asia/Kolkata",
    weekly_capacity: 3,
    available_for_interviews: false,
  })
})

test("candidate joins an in-app human meeting and can leave safely", async ({ page }) => {
  await setCandidateToken(page)
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => new MediaStream() },
    })
  })
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidateActor) }))
  await page.route("**/api/me/interviews/11/join", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      interview_id: 11,
      org_id: 4,
      title: "Technical interview",
      posting_title: posting.title,
      org_name: "Acme",
      scheduled_start: new Date(Date.now() + 5 * 60_000).toISOString(),
      scheduled_end: new Date(Date.now() + 65 * 60_000).toISOString(),
      timezone: "UTC",
      ticket: "short-lived-room-ticket",
      participants: [
        { user_id: 7, name: "Candidate", role: "CANDIDATE", self: true },
        { user_id: 8, name: "Recruiter", role: "INTERVIEWER", self: false },
      ],
    }) })
  })
  await page.routeWebSocket("ws://127.0.0.1:8000/ws/interviews/11", (socket) => {
    socket.send(JSON.stringify({ type: "room_state", interview_id: 11, self_user_id: 7, participants: [] }))
  })

  await page.goto("/meeting/11")
  await expect(page.getByRole("heading", { name: "Technical interview" })).toBeVisible()
  await page.getByRole("button", { name: "Join call" }).click()
  await expect(page.getByText("CONNECTED")).toBeVisible()
  await page.getByRole("button", { name: "Mute" }).click()
  await expect(page.getByRole("button", { name: "Unmute" })).toBeVisible()
  await page.getByRole("button", { name: "Leave" }).click()
  await expect(page).toHaveURL(/\/interviews$/)
})

test("assigned interviewer ends the in-app call and submits an independent scorecard", async ({ page }) => {
  await setRecruiterToken(page)
  const interviewerActor = { ...recruiterActor, capabilities: [...recruiterActor.capabilities, "interview:conduct"] }
  let scorecardBody: Record<string, unknown> | null = null
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => new MediaStream() } })
  })
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(interviewerActor) }))
  await page.route("**/api/me/interviews/12/join", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      interview_id: 12,
      org_id: 4,
      title: "Technical interview",
      posting_title: posting.title,
      org_name: "Acme",
      scheduled_start: new Date(Date.now() + 5 * 60_000).toISOString(),
      scheduled_end: new Date(Date.now() + 65 * 60_000).toISOString(),
      timezone: "UTC",
      ticket: "short-lived-room-ticket",
      participants: [
        { user_id: 8, name: "Interviewer", role: "INTERVIEWER", self: true },
        { user_id: 7, name: "Candidate", role: "CANDIDATE", self: false },
      ],
    }),
  }))
  await page.routeWebSocket("ws://127.0.0.1:8000/ws/interviews/12", (socket) => {
    socket.send(JSON.stringify({ type: "room_state", interview_id: 12, self_user_id: 8, participants: [] }))
  })
  await page.route("**/api/orgs/4/interviews/12/scorecard", async (route) => {
    scorecardBody = route.request().postDataJSON()
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ interview_id: 12, submitted: 1, expected: 1, complete: true, duplicate: false }) })
  })

  await page.goto("/meeting/12")
  await page.getByRole("button", { name: "Join call" }).click()
  await expect(page.getByText("CONNECTED")).toBeVisible()
  await page.getByRole("button", { name: "End call & score" }).click()
  await expect(page.getByRole("heading", { name: "Rate the evidence from this round" })).toBeVisible()
  for (const label of ["Role-specific skills and job requirements", "Problem-solving and reasoning", "Depth of relevant experience", "Job-related communication", "Collaboration and ownership"]) {
    await page.getByRole("combobox", { name: new RegExp(label) }).selectOption("4")
    await page.getByLabel(`${label} · EVIDENCE`).fill(`Observed job-related evidence for ${label.toLowerCase()}.`)
  }
  await page.getByRole("button", { name: "Submit scorecard" }).click()
  await expect(page.getByText(/All panel scorecards are in/)).toBeVisible()
  expect(scorecardBody).toMatchObject({ recommendation: "ADVANCE", ratings: expect.arrayContaining([expect.objectContaining({ score: 4 })]) })
})
