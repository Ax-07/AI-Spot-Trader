import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const foundations = [
  {
    title: "Backend autonome",
    description: "Le moteur FastAPI est une application indépendante du cockpit.",
  },
  {
    title: "PAPER d'abord",
    description: "Aucune exécution LIVE ni logique de trading n'est présente dans ce bootstrap.",
  },
  {
    title: "Frontières claires",
    description: "Kraken, le LLM, le Risk Engine et le Paper Broker arriveront dans des batches dédiés.",
  },
];

export default function Home() {
  return (
    <main className="min-h-svh bg-background px-6 py-16 text-foreground">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-10">
        <section className="space-y-4">
          <p className="text-sm font-medium uppercase tracking-[0.22em] text-muted-foreground">
            Batch 01 · Bootstrap
          </p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            AI Spot Trader
          </h1>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
            Cockpit technique initial. Le frontend visualise et contrôle à terme, mais il ne porte
            aucune logique nécessaire à la survie du moteur de trading.
          </p>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {foundations.map((foundation) => (
            <Card key={foundation.title}>
              <CardHeader>
                <CardTitle>{foundation.title}</CardTitle>
                <CardDescription>{foundation.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <span className="text-sm text-muted-foreground">Socle prêt pour les prochains batches.</span>
              </CardContent>
            </Card>
          ))}
        </section>
      </div>
    </main>
  );
}
