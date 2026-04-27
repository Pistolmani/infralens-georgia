"use client";

import { FormEvent, useEffect, useState } from "react";
import type { components } from "../lib/api";

type IncidentCreateRequest = components["schemas"]["IncidentCreateRequest"];
type IncidentSummaryResponse = components["schemas"]["IncidentSummaryResponse"];
type IncidentAnalyzeResponse = components["schemas"]["IncidentAnalyzeResponse"];
type HttpValidationError = components["schemas"]["HTTPValidationError"];

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const languageOptions = [
  { label: "Auto", value: "" },
  { label: "KA", value: "ka" },
  { label: "EN", value: "en" },
];

function formatCreatedAt(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusClassName(status: IncidentSummaryResponse["status"]): string {
  switch (status) {
    case "analyzed":
      return "border-emerald-300 bg-emerald-50 text-emerald-900";
    case "analysis_failed":
      return "border-rose-300 bg-rose-50 text-rose-900";
    case "queued":
    case "analyzing":
      return "border-sky-300 bg-sky-50 text-sky-900";
    case "created":
    default:
      return "border-zinc-300 bg-zinc-50 text-zinc-800";
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as
    | HttpValidationError
    | { detail?: string }
    | null;

  if (body && typeof body.detail === "string") {
    return body.detail;
  }
  if (body && Array.isArray(body.detail)) {
    return body.detail.map((error) => error.msg).join("; ");
  }
  return `Request failed with status ${response.status}`;
}

export default function Home() {
  const [reportText, setReportText] = useState("");
  const [languageHint, setLanguageHint] = useState("");
  const [locationHint, setLocationHint] = useState("");
  const [recentIncidents, setRecentIncidents] = useState<IncidentSummaryResponse[]>([]);
  const [createdIncident, setCreatedIncident] = useState<IncidentSummaryResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingRecent, setIsLoadingRecent] = useState(true);
  const [activeAnalyzeId, setActiveAnalyzeId] = useState<string | null>(null);

  async function loadRecentIncidents(): Promise<void> {
    setIsLoadingRecent(true);
    try {
      const response = await fetch(`${apiBaseUrl}/incidents?limit=8&offset=0`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }
      const body = (await response.json()) as components["schemas"]["IncidentListResponse"];
      setRecentIncidents(body.items);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to load incidents");
    } finally {
      setIsLoadingRecent(false);
    }
  }

  useEffect(() => {
    void loadRecentIncidents();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setErrorMessage(null);
    setCreatedIncident(null);

    const payload: IncidentCreateRequest = {
      report_text: reportText.trim(),
      language_hint: languageHint || null,
      location_hint: locationHint.trim() || null,
    };

    if (!payload.report_text) {
      setErrorMessage("Report text is required");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/incidents`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const incident = (await response.json()) as IncidentSummaryResponse;
      setCreatedIncident(incident);
      setRecentIncidents((items) => [incident, ...items.filter((item) => item.id !== incident.id)].slice(0, 8));
      setReportText("");
      setLocationHint("");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to create incident");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAnalyze(incidentId: string): Promise<void> {
    setErrorMessage(null);
    setActiveAnalyzeId(incidentId);

    try {
      const response = await fetch(`${apiBaseUrl}/incidents/${incidentId}/analyze`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const body = (await response.json()) as IncidentAnalyzeResponse;
      setRecentIncidents((items) =>
        items.map((incident) =>
          incident.id === body.incident_id
            ? {
                ...incident,
                status: body.status,
              }
            : incident,
        ),
      );
      setCreatedIncident((incident) =>
        incident && incident.id === body.incident_id
          ? {
              ...incident,
              status: body.status,
            }
          : incident,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to queue analysis");
    } finally {
      setActiveAnalyzeId(null);
    }
  }

  const canSubmit = reportText.trim().length > 0 && !isSubmitting;

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-emerald-700">
              InfraLens Georgia
            </p>
            <h1 className="text-xl font-semibold tracking-normal">Incident Intake</h1>
          </div>
          <div className="text-right text-sm text-zinc-600">
            <div className="font-medium text-zinc-950">API</div>
            <div>{apiBaseUrl}</div>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <form onSubmit={handleSubmit} className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="grid gap-4">
            <label className="grid gap-2">
              <span className="text-sm font-medium text-zinc-700">Report text</span>
              <textarea
                className="min-h-48 resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none ring-emerald-700 focus:ring-2"
                placeholder="Streetlights are out on Rustaveli Avenue near the bus stop."
                value={reportText}
                onChange={(event) => setReportText(event.target.value)}
              />
            </label>

            <div className="grid gap-4 sm:grid-cols-[160px_minmax(0,1fr)]">
              <label className="grid gap-2">
                <span className="text-sm font-medium text-zinc-700">Language hint</span>
                <select
                  className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm outline-none ring-emerald-700 focus:ring-2"
                  value={languageHint}
                  onChange={(event) => setLanguageHint(event.target.value)}
                >
                  {languageOptions.map((option) => (
                    <option key={option.value || "auto"} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-zinc-700">Location hint</span>
                <input
                  className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm outline-none ring-emerald-700 focus:ring-2"
                  placeholder="Municipality, street, or landmark"
                  value={locationHint}
                  onChange={(event) => setLocationHint(event.target.value)}
                />
              </label>
            </div>

            {errorMessage ? (
              <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900" role="alert">
                {errorMessage}
              </div>
            ) : null}

            {createdIncident ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-950">
                <div className="font-medium">Created incident</div>
                <div className="mt-1 break-all text-emerald-900">{createdIncident.id}</div>
              </div>
            ) : null}

            <div className="flex justify-end border-t border-zinc-200 pt-4">
              <button
                type="submit"
                className="h-10 rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
                disabled={!canSubmit}
              >
                {isSubmitting ? "Creating..." : "Create Incident"}
              </button>
            </div>
          </div>
        </form>

        <aside className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold">Recent Incidents</h2>
            <button
              type="button"
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-800 disabled:opacity-50"
              onClick={() => void loadRecentIncidents()}
              disabled={isLoadingRecent}
            >
              Refresh
            </button>
          </div>

          <div className="mt-4 grid gap-3">
            {isLoadingRecent ? (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm text-zinc-600">
                Loading incidents
              </div>
            ) : null}

            {!isLoadingRecent && recentIncidents.length === 0 ? (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm text-zinc-600">
                No incidents yet
              </div>
            ) : null}

            {recentIncidents.map((incident) => (
              <article key={incident.id} className="rounded-md border border-zinc-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span
                    className={`rounded border px-2 py-0.5 text-xs font-semibold ${statusClassName(incident.status)}`}
                  >
                    {incident.status.replace("_", " ")}
                  </span>
                  <time className="text-xs text-zinc-500">{formatCreatedAt(incident.created_at)}</time>
                </div>
                <p className="mt-3 line-clamp-3 text-sm leading-6 text-zinc-800">{incident.original_text}</p>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <div className="break-all font-mono text-xs text-zinc-500">{incident.id}</div>
                  <button
                    type="button"
                    className="h-8 shrink-0 rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={() => void handleAnalyze(incident.id)}
                    disabled={
                      activeAnalyzeId === incident.id ||
                      incident.status === "queued" ||
                      incident.status === "analyzing" ||
                      incident.status === "analyzed"
                    }
                  >
                    {activeAnalyzeId === incident.id ? "Queuing" : "Analyze"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
