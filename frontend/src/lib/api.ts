import axios from "axios";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE,
});

export interface JobDescription {
  job_title: string;
  job_description: string;
  skills: string;
  experience: string;
  qualifications: string;
}

export interface Candidate {
  resume_id: string;
  headline: string | null;
  composite_score: number;
  band: "Strong Fit" | "High Potential" | "Needs Review" | "Low Fit";
  semantic_score: number;
  skill_score: number;
  experience_score: number;
  education_score: number;
  matched_skills: string[];
  missing_skills: string[];
  years_experience: number | null;
  education: string[];
  job_titles: string[];
  companies: string[];
  integrity_status:
    | "CLEAR"
    | "WARNING"
    | "POTENTIAL MANIPULATION"
    | "UNKNOWN";
  explanation: string;
  explanation_source: string;
}

export interface IntegrityEvidence {
  check: string;
  detail: string;
  flagged_text: string;
  page: number | null;
}

export interface CandidateDetail extends Candidate {
  integrity_evidence: IntegrityEvidence[];
}

export interface ScreeningStatus {
  status: "pending" | "running" | "done" | "error";
  step: string | null;
  step_label: string;
  progress: number;
  error: string | null;
}

export interface ScreeningSummary {
  status: string;
  job_description: JobDescription;
  data_mode: "live" | "demo";
  band_counts: Record<string, number>;
  flagged_count: number;
  bias_summary: {
    n_candidates: number;
    mean_score_delta: number;
    max_abs_score_delta: number;
  };
  total_candidates: number;
}

export interface WhatIfResult {
  resume_id: string;
  headline: string | null;
  original_composite_score: number;
  new_composite_score: number;
  original_band: string;
  new_band: string;
  qualified: boolean;
  missing_mandatory: string[];
}

export interface RecentScreening {
  screening_id: string;
  job_title: string;
  data_mode: string;
  n_candidates: number;
  n_shortlisted: number;
  n_strong: number;
  n_flagged: number;
  created_at: string;
  status: string;
}

export async function createScreening(params: {
  jobTitle: string;
  jobDescription: string;
  skills: string;
  experience: string;
  qualification: string;
  topK: number;
  resumes: File[];
}): Promise<{ screening_id: string }> {
  const form = new FormData();

  form.append("job_title", params.jobTitle);
  form.append("job_description", params.jobDescription);
  form.append("skills", params.skills);
  form.append("experience", params.experience);
  form.append("qualification", params.qualification);
  form.append("top_k", String(params.topK));

  params.resumes.forEach((file) => {
    form.append("resumes", file);
  });

  const res = await api.post("/api/screenings", form);

  return res.data;
}

export async function createDemoScreening(): Promise<{
  screening_id: string;
}> {
  const res = await api.post("/api/screenings/demo");

  return res.data;
}

export async function getScreeningStatus(
  id: string
): Promise<ScreeningStatus> {
  const res = await api.get(`/api/screenings/${id}/status`);

  return res.data;
}

export async function getScreeningSummary(
  id: string
): Promise<ScreeningSummary> {
  const res = await api.get(`/api/screenings/${id}`);

  return res.data;
}

export async function getCandidates(
  id: string,
  opts?: {
    band?: string;
    flaggedOnly?: boolean;
  }
): Promise<{
  candidates: Candidate[];
  count: number;
}> {
  const res = await api.get(`/api/screenings/${id}/candidates`, {
    params: {
      band: opts?.band,
      flagged_only: opts?.flaggedOnly,
    },
  });

  return res.data;
}

export async function getCandidateDetail(
  id: string,
  resumeId: string
): Promise<CandidateDetail> {
  const res = await api.get(
    `/api/screenings/${id}/candidates/${resumeId}`
  );

  return res.data;
}

export async function getWhatIfSkills(
  id: string
): Promise<string[]> {
  const res = await api.get(
    `/api/screenings/${id}/whatif/skills`
  );

  return res.data.skills;
}

export async function recomputeWhatIf(
  id: string,
  toggles: Record<string, string>
): Promise<{
  results: WhatIfResult[];
  summary: {
    total_candidates: number;
    qualified_count: number;
  };
}> {
  const res = await api.post(
    `/api/screenings/${id}/whatif/recompute`,
    { toggles }
  );

  return res.data;
}

export function pdfReportUrl(id: string) {
  return `${API_BASE}/api/screenings/${id}/report/pdf`;
}

export function excelReportUrl(id: string) {
  return `${API_BASE}/api/screenings/${id}/report/excel`;
}

export async function getDashboardSummary(): Promise<{
  total_screened: number;
  total_shortlisted: number;
  total_strong: number;
  total_flagged: number;
  total_screenings: number;
}> {
  const res = await api.get("/api/dashboard/summary");

  return res.data;
}

export async function getRecentScreenings(
  limit = 10
): Promise<RecentScreening[]> {
  const res = await api.get(
    "/api/dashboard/recent-screenings",
    {
      params: { limit },
    }
  );

  return res.data.screenings;
}