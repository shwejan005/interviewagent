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
  active_org_id: number | null;
  active_role: string | null;
  capabilities: string[];
  memberships: Membership[];
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
  org_name?: string;
  org_slug?: string;
  created_at: string;
};

export type Campaign = {
  id: number;
  org_id: number;
  name: string;
  description: string;
  status: string;
  created_at: string;
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
