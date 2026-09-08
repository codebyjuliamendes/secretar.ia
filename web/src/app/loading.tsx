import { Spinner } from "@/components/ui/primitives";

export default function Loading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center" role="status" aria-label="Carregando">
      <Spinner className="h-6 w-6 text-primary" />
    </div>
  );
}
