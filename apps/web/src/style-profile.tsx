import { useEffect, useState } from "react";
import { apiFetch } from "./api";

type Profile = {
  mode: "profile" | "image";
  status: "no_anchor" | "ready" | "analyzing" | "measured_only";
  palette?: { hex: string; share: number; name: string }[];
  materials?: { substance: string; colour: string; finish: string; wear: string }[];
  rendering?: string | null;
  stylization?: string | null;
};

const statusText: Record<Profile["status"], string> = {
  no_anchor: "",
  ready: "Analyzed locally. Concepts use these materials and colours; the anchor's shape is never copied.",
  analyzing: "Analyzing the anchor locally… concepts wait for it in Auto.",
  measured_only: "Measured colours only. The material analysis runs automatically before the next Auto generation.",
};

// Read-only summary of the shape-free style profile extracted from the project's style anchor.
export function StyleProfileCard({ projectId, anchorId, mode }: { projectId: string; anchorId: string; mode: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const response = await apiFetch(`/api/projects/${projectId}/style-profile`);
        if (!response.ok) return;
        const value = (await response.json()) as Profile;
        if (!alive) return;
        setProfile(value);
        if (value.status === "analyzing") timer = window.setTimeout(load, 5000);
      } catch {
        /* Informational card; Settings stays usable offline. */
      }
    };
    load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [projectId, anchorId, mode]);
  if (!profile || profile.status === "no_anchor" || profile.mode === "image") return null;
  return (
    <div className="style-profile-card" aria-live="polite">
      <div className="style-profile-swatches" role="list" aria-label="Measured palette">
        {(profile.palette || []).map((entry) => (
          <span key={entry.hex} role="listitem" title={`${entry.name} · ${entry.hex} · ${Math.round(entry.share * 100)}%`} style={{ background: entry.hex, flexGrow: Math.max(1, Math.round(entry.share * 100)) }} />
        ))}
      </div>
      {!!profile.materials?.length && (
        <ul className="style-profile-materials">
          {profile.materials.map((m) => (
            <li key={`${m.colour}-${m.substance}`}>
              {m.colour} {m.substance} <small>{m.finish}{m.wear !== "clean" ? `, ${m.wear.replace("_", " ")}` : ""}</small>
            </li>
          ))}
        </ul>
      )}
      {profile.rendering && <p className="style-profile-rendering">{profile.rendering}{profile.stylization ? ` · ${profile.stylization.replace("_", "-")}` : ""}</p>}
      <small>{statusText[profile.status]}</small>
    </div>
  );
}
