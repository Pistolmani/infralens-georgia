const runtimeItems = [
  ["API", "FastAPI scaffold"],
  ["Data", "PostgreSQL + pgvector"],
  ["Queue", "Redis / RQ"],
  ["Models", "Local Ollama"],
];

export default function Home() {
  return (
    <main className="min-h-screen bg-stone-50 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
              InfraLens Georgia
            </p>
            <h1 className="text-xl font-semibold tracking-normal">Incident Intake</h1>
          </div>
          <span className="rounded border border-amber-300 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-900">
            Milestone 1
          </span>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <form className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="grid gap-4">
            <label className="grid gap-2">
              <span className="text-sm font-medium text-zinc-700">Report text</span>
              <textarea
                className="min-h-44 resize-y rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm outline-none ring-emerald-700 focus:ring-2"
                placeholder="Streetlight report text"
                disabled
              />
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-2">
                <span className="text-sm font-medium text-zinc-700">Language hint</span>
                <input
                  className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm"
                  placeholder="ka or en"
                  disabled
                />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-zinc-700">Location hint</span>
                <input
                  className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm"
                  placeholder="Municipality, street, landmark"
                  disabled
                />
              </label>
            </div>

            <div className="flex items-center justify-between border-t border-zinc-200 pt-4">
              <p className="text-sm text-zinc-600">API contract pending</p>
              <button
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-semibold text-white opacity-50"
                disabled
              >
                Create Incident
              </button>
            </div>
          </div>
        </form>

        <aside className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold">Runtime</h2>
          <dl className="mt-4 grid gap-3">
            {runtimeItems.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 border-b border-zinc-100 pb-3">
                <dt className="text-sm font-medium text-zinc-600">{label}</dt>
                <dd className="text-right text-sm text-zinc-950">{value}</dd>
              </div>
            ))}
          </dl>
        </aside>
      </section>
    </main>
  );
}

