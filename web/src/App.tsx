import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { fetchHealth } from "./api/client";

const queryClient = new QueryClient();

function HealthCheck() {
  const { data, error, isPending } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (isPending) return <p>Checking API connection…</p>;
  if (error) return <p>API unreachable: {error.message}</p>;
  return <p>API status: {data.status}</p>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <main>
        <h1>Goodgorithm</h1>
        <HealthCheck />
      </main>
    </QueryClientProvider>
  );
}
