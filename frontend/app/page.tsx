import Link from 'next/link';

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center justify-center">
        <section className="w-full max-w-4xl px-6 py-10 text-center sm:px-10 sm:py-14">
          <div className="mx-auto mb-6 inline-flex px-4 py-1 text-xs font-semibold uppercase tracking-[0.38em] text-slate-100 [text-shadow:0_8px_28px_rgba(15,23,42,0.55)]">
            Splice Playground
          </div>

          <h1 className="mx-auto max-w-4xl text-5xl font-black tracking-[-0.05em] text-white [text-shadow:0_18px_50px_rgba(15,23,42,0.58)] sm:text-7xl lg:text-8xl">
            Visualize
            <br />
            Splicing Into
            <br />
            Structure
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-sm leading-7 text-slate-100 [text-shadow:0_10px_34px_rgba(15,23,42,0.58)] sm:text-lg">
            DNA editing, transcript consequences, and protein structure prediction in one continuous flow.
          </p>

          <div className="mt-10 flex items-center justify-center">
            <Link
              href="/select-mutant"
              className="inline-flex items-center rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-10 py-4 text-base font-bold text-white shadow-[0_20px_50px_rgba(2,132,199,0.35)] transition hover:scale-[1.02] hover:brightness-105"
            >
              Start
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
