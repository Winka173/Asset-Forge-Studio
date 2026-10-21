import "./activity-indicator.css";

type Props = {
  label: string;
  detail?: string;
  /** Only supply measured backend progress. Omit for an indeterminate stage. */
  progress?: number | null;
  compact?: boolean;
};

/** Render only while a real request or job is active. Animation never invents progress. */
export function ActivityIndicator({ label, detail, progress, compact = false }: Props) {
  const measured = typeof progress === "number" && Number.isFinite(progress)
    ? Math.max(0, Math.min(100, progress)) : null;
  return <div className={`afs-activity${compact ? " afs-activity-compact" : ""}`} role="status" aria-live="polite" aria-atomic="true">
    <span className="afs-activity-orbit" aria-hidden="true"><i /><i /><i /></span>
    <div className="afs-activity-copy">
      <strong>{label}</strong>
      {detail && <span>{detail}</span>}
      {!compact && <div className={`afs-activity-track${measured === null ? " is-indeterminate" : ""}`}
        role={measured === null ? undefined : "progressbar"}
        aria-label={measured === null ? undefined : label}
        aria-valuemin={measured === null ? undefined : 0}
        aria-valuemax={measured === null ? undefined : 100}
        aria-valuenow={measured ?? undefined}>
        <span style={measured === null ? undefined : { width: `${measured}%` }} />
      </div>}
    </div>
    {measured !== null && <span className="afs-activity-value">{Math.round(measured)}%</span>}
  </div>;
}
