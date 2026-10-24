import { useState } from "react";
import { apiUrl } from "./api";

type Image = { id: string; name: string; url: string };

// Pick a project image by sight instead of by file name; newest first, collapsed to one row until expanded.
export function ImagePicker({ label, images, value, onChange, noneLabel, limit = 11 }: { label: string; images: Image[]; value: string; onChange: (id: string) => void; noneLabel: string; limit?: number }) {
  const [all, setAll] = useState(false);
  const ordered = images.slice().reverse();
  const shown = all ? ordered : ordered.slice(0, limit);
  if (!all && value && !shown.some((i) => i.id === value)) { const chosen = ordered.find((i) => i.id === value); if (chosen) shown.unshift(chosen); }
  return (
    <div className="reference-picker" role="group" aria-label={label}>
      <div className="reference-picker-grid">
        <button type="button" className={!value ? "selected" : ""} aria-pressed={!value} onClick={() => onChange("")}><span className="reference-picker-none">{noneLabel}</span></button>
        {shown.map((image) => (
          <button key={image.id} type="button" className={value === image.id ? "selected" : ""} aria-pressed={value === image.id} title={image.name} onClick={() => onChange(image.id)}>
            <img src={apiUrl(image.url)} alt={image.name} loading="lazy" />
          </button>
        ))}
      </div>
      {images.length > limit && <button type="button" className="text-button" onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${images.length} images`}</button>}
    </div>
  );
}
