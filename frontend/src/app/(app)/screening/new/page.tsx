"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { Sparkles, FileUp } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { SkillChipInput } from "@/components/screening/skill-chip-input";
import { ResumeDropzone } from "@/components/screening/resume-dropzone";
import { ProcessingProgress } from "@/components/screening/processing-progress";
import { useScreening } from "@/lib/screening-context";
import { createScreening, createDemoScreening, getScreeningStatus } from "@/lib/api";

const EXPERIENCE_OPTIONS = ["0 to 2 Years", "2 to 5 Years", "5 to 8 Years", "8 to 12 Years", "12+ Years"];
const QUALIFICATION_OPTIONS = ["High School Diploma", "Associate's Degree", "Bachelor's Degree", "Master's Degree", "PhD"];

export default function NewScreeningPage() {
  const router = useRouter();
  const { setActiveScreeningId } = useScreening();

  const [dataSource, setDataSource] = React.useState<"live" | "demo">("live");

  const [jobTitle, setJobTitle] = React.useState("");
  const [jobDescription, setJobDescription] = React.useState("");
  const [skills, setSkills] = React.useState<string[]>([]);
  const [experience, setExperience] = React.useState("");
  const [qualification, setQualification] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [topK, setTopK] = React.useState<string>("");

  const [submitting, setSubmitting] = React.useState(false);
  const [screeningId, setScreeningId] = React.useState<string | null>(null);
  const [progressState, setProgressState] = React.useState<{ step: string | null; progress: number }>({
    step: null, progress: 0,
  });
  const [error, setError] = React.useState<string | null>(null);

  const nUploaded = files.length;
  const topKNum = parseInt(topK, 10);
  const topKError =
    nUploaded === 0 ? null :
    topK.trim() === "" ? "Enter the number of resumes to shortlist." :
    isNaN(topKNum) || topKNum <= 0 ? "Must be a positive whole number." :
    topKNum > nUploaded ? `Cannot exceed the number of uploaded resumes (${nUploaded}).` : null;

  const canRunLive = jobDescription.trim().length > 0 && nUploaded > 0 && !topKError && topKNum > 0;

  React.useEffect(() => {
    if (nUploaded > 0 && topK === "") setTopK(String(nUploaded));
  }, [nUploaded]); // eslint-disable-line react-hooks/exhaustive-deps

  async function pollUntilDone(id: string) {
    for (let i = 0; i < 300; i++) {
      const status = await getScreeningStatus(id);
      setProgressState({ step: status.step, progress: status.progress });
      if (status.status === "done") {
        setActiveScreeningId(id);
        router.push(`/screening/${id}/shortlist`);
        return;
      }
      if (status.status === "error") {
        setError(status.error || "Screening failed.");
        setSubmitting(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 1200));
    }
    setError("Screening is taking longer than expected. Please try again.");
    setSubmitting(false);
  }

  async function handleRunLive() {
    setSubmitting(true);
    setError(null);
    try {
      const { screening_id } = await createScreening({
        jobTitle: jobTitle || "Untitled Role",
        jobDescription,
        skills: skills.join(", "),
        experience,
        qualification,
        topK: topKNum,
        resumes: files,
      });
      setScreeningId(screening_id);
      pollUntilDone(screening_id);
    } catch {
      setError("Could not start the screening. Please check your input and try again.");
      setSubmitting(false);
    }
  }

  async function handleRunDemo() {
    setSubmitting(true);
    setError(null);
    try {
      const { screening_id } = await createDemoScreening();
      setScreeningId(screening_id);
      pollUntilDone(screening_id);
    } catch {
      setError("Could not start the sample screening. Please try again.");
      setSubmitting(false);
    }
  }

  if (submitting || screeningId) {
    return (
      <div className="max-w-xl mx-auto mt-10">
        <Card className="p-8">
          <div className="flex flex-col items-center text-center mb-6">
            <div className="h-12 w-12 rounded-full bg-accent-light text-accent-hover flex items-center justify-center mb-3">
              <Sparkles size={22} />
            </div>
            <h2 className="text-lg font-semibold text-foreground">Running AI Screening</h2>
            <p className="text-sm text-muted mt-1">This usually takes under a minute.</p>
          </div>
          {error ? (
            <div className="text-sm text-band-low bg-band-low-bg border border-red-200 rounded-md p-3 text-center">
              {error}
            </div>
          ) : (
            <ProcessingProgress currentStep={progressState.step} progress={progressState.progress} />
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Create a New Screening</h2>
        <p className="text-sm text-muted mt-1">
          Upload a job description and candidate resumes to identify the strongest matches.
        </p>
      </div>

      <Card className="p-5">
        <div className="text-xs font-semibold text-muted mb-2.5">Data Source</div>
        <div className="inline-flex rounded-lg border border-border bg-background p-1 gap-1">
          <button
            onClick={() => setDataSource("live")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              dataSource === "live" ? "bg-white shadow-sm text-foreground border border-border" : "text-muted hover:text-foreground"
            }`}
          >
            Upload Your Own
          </button>
          <button
            onClick={() => setDataSource("demo")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              dataSource === "demo" ? "bg-white shadow-sm text-foreground border border-border" : "text-muted hover:text-foreground"
            }`}
          >
            Use Sample Data
          </button>
        </div>
      </Card>

      {dataSource === "demo" ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Sample Screening</CardTitle>
              <Badge variant="flagged">Fictional demo content</Badge>
            </div>
            <CardDescription>
              A small bundled job description and 6 sample resumes — including one with deliberately
              hidden content, to demonstrate the integrity check. No real data is used.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button size="lg" onClick={handleRunDemo} className="gap-2">
              <Sparkles size={16} /> Run AI Screening
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Job Description</CardTitle>
                <CardDescription>What role are you screening candidates for?</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div>
                  <label className="text-xs font-medium text-muted mb-1.5 block">Job Title</label>
                  <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="e.g. Machine Learning Engineer" />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted mb-1.5 block">Job Description</label>
                  <Textarea
                    value={jobDescription} onChange={(e) => setJobDescription(e.target.value)}
                    placeholder="Paste the full job description here..." className="min-h-32"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted mb-1.5 block">Required Skills</label>
                  <SkillChipInput value={skills} onChange={setSkills} placeholder="Type a skill and press Enter…" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted mb-1.5 block">Experience Required</label>
                    <Select value={experience} onValueChange={setExperience}>
                      <SelectTrigger><SelectValue placeholder="Select range" /></SelectTrigger>
                      <SelectContent>
                        {EXPERIENCE_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted mb-1.5 block">Qualification</label>
                    <Select value={qualification} onValueChange={setQualification}>
                      <SelectTrigger><SelectValue placeholder="Select qualification" /></SelectTrigger>
                      <SelectContent>
                        {QUALIFICATION_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Candidate Resumes</CardTitle>
                <CardDescription>Upload PDF resumes for AI-powered screening</CardDescription>
              </CardHeader>
              <CardContent>
                <ResumeDropzone files={files} onChange={setFiles} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Screening Configuration</CardTitle>
              <CardDescription>How many candidates should be shortlisted?</CardDescription>
            </CardHeader>
            <CardContent className="flex items-end gap-4 flex-wrap">
              <div className="w-40">
                <label className="text-xs font-medium text-muted mb-1.5 block">Top-K to shortlist</label>
                <Input
                  value={topK} onChange={(e) => setTopK(e.target.value)} placeholder="e.g. 10" inputMode="numeric"
                />
              </div>
              <div className="text-xs text-muted pb-2">
                {nUploaded > 0 ? `${nUploaded} candidates available` : "Upload resumes to continue"}
              </div>
              {topKError && <div className="text-xs text-band-low w-full">{topKError}</div>}
              <div className="w-full flex justify-end">
                <Button size="lg" disabled={!canRunLive} onClick={handleRunLive} className="gap-2">
                  <FileUp size={16} /> Run AI Screening
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
