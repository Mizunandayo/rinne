import type { ReconstructionResult } from "@rinne/contracts";

const LABELS: Record<string, string> = {
  fieldDecisiveness: "Field decisiveness",
  watertightness: "Watertightness",
  volumePlausibility: "Volume plausibility",
  foregroundQuality: "Foreground quality",
};

const percent = (value: number): string => `${(value * 100).toFixed(1)}%`;

interface ConfidenceReadoutProps {
  readonly confidence: ReconstructionResult["confidence"];
}

export function ConfidenceReadout({ confidence }: ConfidenceReadoutProps) {
  const { score, band, calibrated, components, weights } = confidence;
  const entries = Object.entries(components) as [string, number][];
  // Object.entries rather than an index signature
  const weightOf = new Map(Object.entries(weights) as [string, number][]);

  return (
    <section className="rinne-confidence" aria-label="Reconstruction confidence">
      <p className="rinne-caption">Reconstruction confidence</p>
      <p className="rinne-confidence-score">{percent(score)}</p>

      <div
        className="rinne-meter"
        role="meter"
        aria-valuenow={Math.round(score * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Confidence"
      >
        <div className="rinne-meter-fill" style={{ width: `${score * 100}%` }} />
      </div>

      <p className="rinne-confidence-band">
        {`Band: ${band}`}
        {calibrated ? "" : " · thresholds are documented guesses, not measured"}
      </p>

      <dl className="rinne-components">
        {entries.map(([name, value]) => {
          const weight = weightOf.get(name) ?? 0;
          return (
            <div key={name} className="rinne-component">
              <dt>{LABELS[name] ?? name}</dt>
              <dd>
                <span className="rinne-component-value">{percent(value)}</span>
                {/* The weight ships in the payload so the score is recomputable
                    from the response alone. Showing it is the point. */}
                <span className="rinne-caption">{`weight ${weight.toFixed(4)}`}</span>
                <div className="rinne-meter rinne-meter-small">
                  <div className="rinne-meter-fill" style={{ width: `${value * 100}%` }} />
                </div>
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
