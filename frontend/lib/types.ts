/**
 * Shared domain types mirroring backend/hiring_models.py and the response
 * shapes documented in docs/API_REFERENCE.md. Kept intentionally loose in a
 * few places (e.g. `verdict: unknown`) where the backend genuinely returns
 * agent-shaped JSON rather than a fixed contract — forcing a precise type
 * there would just relocate the `any` instead of removing it.
 */

export type Membership = {
  org_id: number;
  org_name: string;
  org_slug: string;
  role_name: string;
};

export type Actor = {
  user_id: number;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  email_verified_at?: string | null;
  email_verification_required?: boolean;
  impersonated_by?: number | null;
  active_org_id: number | null;
  active_role: string | null;
  capabilities: string[];
  memberships: Membership[];
};

export type UserNotification = {
  id: number;
  org_id: number | null;
  application_id: number | null;
  notification_type: string;
  title: string;
  body: string;
  href: string;
  metadata: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
};

export type WorkExperience = {
  id: number;
  company: string;
  title: string;
  location: string;
  start_date: string;
  end_date: string | null;
  is_current: boolean | number;
  description: string;
};

export type Education = {
  id: number;
  institution: string;
  degree: string;
  field: string;
  start_year: number | null;
  end_year: number | null;
};

export type Skill = {
  id: number;
  skill: string;
  skill_normalized: string;
  years: number | null;
  verified: boolean | number;
  verified_source: string | null;
};

export type Preferences = {
  desired_roles: string[];
  locations: string[];
  remote_preference: string;
  min_salary: number | null;
  max_salary: number | null;
  currency: string;
  notice_period_days: number | null;
} | null;

export type CandidateProfile = {
  id: number;
  user_id: number;
  headline: string;
  summary: string;
  location: string;
  phone: string;
  work_authorization: string;
  years_experience: number | null;
  open_to_work: boolean | number;
  is_discoverable: boolean | number;
  resume_text: string;
  data_consent_at: string | null;
  updated_at: string;
  experiences: WorkExperience[];
  education: Education[];
  skills: Skill[];
  preferences: Preferences;
  vault_answers: Record<string, string>;
};

export type ResumeParsedSkill = {
  skill: string;
  years: number | null;
};

export type ResumeParsedWorkExperience = {
  company: string;
  title: string;
  location: string;
  start_date: string;
  end_date: string | null;
  is_current: boolean;
  description: string;
};

export type ResumeParsedEducation = {
  institution: string;
  degree: string;
  field: string;
  start_year: number | null;
  end_year: number | null;
};

export type ParsedProfile = {
  headline: string;
  summary: string;
  location: string;
  phone: string;
  work_authorization: string;
  years_experience: number | null;
  skills: ResumeParsedSkill[];
  work_experiences: ResumeParsedWorkExperience[];
  education: ResumeParsedEducation[];
};

export type ResumeParseResponse = {
  resume_document_id: number;
  char_count: number;
  parsed_by: "llm" | "heuristic";
  raw_text: string;
  parsed: ParsedProfile;
  warnings: string[];
};

export type ResumeImportRequest = ParsedProfile & {
  resume_text: string;
};

export type PostingCriterion = {
  key: string;
  label: string;
  weight: number;
  description: string;
  category?: "TECHNICAL" | "BEHAVIORAL";
};

export type CriteriaResponse = {
  posting_id: number;
  competencies: PostingCriterion[];
  custom_questions: string[];
  pass_threshold: number;
  interview_settings: InterviewSettings;
  rubric_version: string;
  updated_at: string;
};

export type InterviewSettings = {
  role_level: "ENTRY" | "MID" | "SENIOR";
  technical_question_count: number;
  behavioral_question_count: number;
  max_followups_per_question: number;
  invitation_window_days: number;
};

export type CriteriaDraft = Pick<CriteriaResponse, "competencies" | "custom_questions" | "pass_threshold" | "interview_settings">;

export type CompetencyScore = {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  evidence: string;
};

export type ApplicationReportResponse = {
  application_id: number;
  evaluation_id: number;
  posting_id: number;
  competency_scores: CompetencyScore[];
  overall_weighted_score: number | null;
  recommendation: string;
  rubric_version: string;
  generated_at: string;
  interview_details: {
    source?: string;
    requirements_coverage?: Array<{
      key: string;
      label: string;
      kind: "COMPETENCY" | "MUST_HAVE" | "RESUME_CLAIM";
      status: "DEMONSTRATED" | "PARTIAL" | "CLAIMED_ONLY" | "NOT_ASSESSED" | "GAP";
      score: number | null;
      weight: number;
      evidence: string;
      resume_evidence?: string;
    }>;
    resume_claims?: Array<{
      claim: string;
      status: "CONFIRMED_IN_INTERVIEW" | "NOT_PROBED" | "WORTH_FOLLOW_UP";
      source?: string | null;
      resume_evidence: string;
      interview_evidence: string;
    }>;
    strengths?: Array<{ text: string; turn_sequence: number; evidence_quote: string }>;
    concerns?: Array<{ text: string; turn_sequence: number; evidence_quote: string }>;
    next_round_focus?: Array<{ requirement: string; status: string }>;
    fit_nudge?: {
      band: "STRONG_FIT" | "LIKELY_FIT" | "MIXED" | "UNLIKELY_FIT" | "INSUFFICIENT_EVIDENCE";
      suggested_action: "PROMOTE" | "HOLD";
      score_threshold: number;
      evidence_coverage_percent: number;
      summary: string;
      calibration: string;
    };
    screening?: {
      decision?: string;
      score?: number;
      policy_version?: string;
      constraint_gaps?: string[];
      evidence?: Array<{ criterion_key: string; status: string; source?: string | null; quote?: string; rationale?: string }>;
    };
    interview?: {
      role_level?: string;
      turn_count?: number;
      weighted_score_status?: string;
      human_decision_required?: boolean;
      turns?: Array<{
        sequence_no: number;
        phase: "TECHNICAL" | "BEHAVIORAL";
        question_type: "CORE" | "FOLLOW_UP";
        competency_key: string;
        difficulty: number;
        question: string;
        answer: string | null;
        answer_source?: "TEXT" | "VOICE";
        assessment: { score?: number; evidence_quote?: string; summary?: string; gaps?: string[] };
      }>;
    };
  };
};

export type AIInterviewTurn = {
  id: number;
  sequence_no: number;
  phase: "TECHNICAL" | "BEHAVIORAL";
  question_type: "CORE" | "FOLLOW_UP";
  competency_key: string;
  difficulty: number;
  question_text: string;
  draft_answer_text?: string;
  draft_updated_at?: string | null;
  answer_text: string | null;
  answer_source?: "TEXT" | "VOICE";
  state: "ASKED" | "ANSWER_QUEUED" | "ASSESSED";
};

export type CandidateAIInterview = {
  application_id: number;
  status: string;
  phase: string;
  rubric_version: string;
  role_level: string;
  candidate_notice_version: string;
  modality?: "TEXT" | "VOICE";
  consent_required: boolean;
  invitation_expires_at?: string | null;
  current_question: AIInterviewTurn | null;
  turns: AIInterviewTurn[];
  message: string;
};

export type ScreeningQuestion = {
  key: string;
  text: string;
  required: boolean;
};

export type JobPosting = {
  id: number;
  org_id: number;
  campaign_id: number;
  title: string;
  description: string;
  location: string;
  employment_type: string;
  remote_policy: string;
  min_experience: number | null;
  max_experience: number | null;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  required_skills: string[];
  screening_questions: ScreeningQuestion[];
  status: "DRAFT" | "PUBLISHED" | "CLOSED";
  auto_reject_enabled: boolean;
  deleted_at?: string | null;
  org_name?: string;
  org_slug?: string;
  created_at: string;
  applicant_count?: number;
};

export type CampaignPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export type Campaign = {
  id: number;
  org_id: number;
  name: string;
  description: string;
  status: "ACTIVE" | "CLOSED";
  department: string;
  hiring_manager: string;
  priority: CampaignPriority;
  target_hires: number | null;
  target_close_date: string | null;
  created_at: string;
  deleted_at?: string | null;
  posting_count?: number;
  applicant_count?: number;
};

export type ApplicationSummary = {
  id: number;
  status: string;
  current_stage: string;
  created_at: string;
  updated_at: string;
  withdrawn_at: string | null;
  posting_id: number;
  posting_title: string;
  location: string;
  remote_policy: string;
  org_name: string;
  ai_interview_status?: string | null;
  ai_interview_phase?: string | null;
};

export type ApplicationDetail = {
  id: number;
  org_id: number;
  posting_id: number;
  candidate_user_id: number;
  status: string;
  current_stage: string;
  source: string;
  created_at: string;
  updated_at: string;
  candidate_name?: string;
  candidate_email?: string;
  profile_snapshot: Record<string, unknown>;
  ai_interview_status?: string | null;
  ai_interview_phase?: string | null;
};

export type ApplicationEvent = {
  event_type: string;
  from_stage?: string | null;
  to_stage: string | null;
  created_at: string;
  note?: string;
};

export type MatchResult = {
  score: number;
  components: Record<string, number>;
  matched_skills: string[];
  missing_skills: string[];
  explanation: string;
};

export type JobRecommendation = MatchResult & {
  posting_id: number;
  title: string;
  org_name: string;
  location: string;
  remote_policy: string;
};

export type CandidateRecommendation = MatchResult & {
  user_id: number;
  full_name: string;
  headline: string;
  location: string;
  years_experience: number | null;
};

export type Referral = {
  id: number;
  org_id: number;
  posting_id: number;
  candidate_email: string;
  note: string;
  status: "PENDING" | "APPLIED" | "DECLINED";
  created_at: string;
  posting_title?: string;
  org_name?: string;
};

export type FunnelStage = {
  stage: string;
  reached: number;
  conversion_from_previous_stage: number | null;
  conversion_from_applied: number | null;
};

export type FunnelResult = {
  funnel: FunnelStage[];
  rejected: number;
  withdrawn: number;
};

export type SelectionRatesResult = {
  segment_by: string;
  segments: Record<string, { total: number; selected: number; selection_rate: number }>;
  adverse_impact_ratio: number | null;
  flag_adverse_impact: boolean;
  note: string;
};

export type AnalyticsTotals = {
  applications: number;
  active: number;
  hired: number;
  rejected: number;
  withdrawn: number;
  open_postings: number;
  avg_time_to_hire_days: number | null;
  conversion_rate: number | null;
};

export type AnalyticsTrendPoint = {
  date: string;
  applications: number;
  hires: number;
};

export type StageDistributionPoint = {
  stage: string;
  count: number;
};

export type SourceBreakdownPoint = {
  source: string;
  applications: number;
  hired: number;
};

export type CampaignPerformancePoint = {
  campaign_id: number;
  name: string;
  applications: number;
  hired: number;
  postings: number;
};

export type TopPostingPoint = {
  posting_id: number;
  title: string;
  applications: number;
  hired: number;
};

export type AnalyticsOverview = {
  totals: AnalyticsTotals;
  trend: AnalyticsTrendPoint[];
  stage_distribution: StageDistributionPoint[];
  source_breakdown: SourceBreakdownPoint[];
  campaign_performance: CampaignPerformancePoint[];
  top_postings: TopPostingPoint[];
};
