export function Placeholder({ title }: { title: string }) {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-mauve">{title}</h1>
      <p className="text-subtext-0">
        This page is scaffolded but not yet implemented. See the KITT 2.0
        roadmap in the repository README for the order pages come online.
      </p>
    </div>
  );
}
