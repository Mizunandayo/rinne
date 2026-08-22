
export function SettlingLoader({ label = "Working" }: { readonly label?: string }) {
  return (
    <div className="rinne-loader" role="status" aria-live="polite">
      <div className="rinne-loader-stage" aria-hidden="true">
        <span className="rinne-loader-bar" data-index="0" />
        <span className="rinne-loader-bar" data-index="1" />
        <span className="rinne-loader-bar" data-index="2" />
        <span className="rinne-loader-ground" />
      </div>
      <span className="rinne-caption">{label}</span>
    </div>
  );
}
