"use client";

import { useState, type FormEvent } from "react";
import { useTenant } from "@/app/app/[tenantId]/layout";
import { Modal } from "@/components/ui/modal";
import { Alert, Button, Field, Input, Select } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import { toLocalInputValue } from "@/lib/format";
import type { Service } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

export function NewAppointmentModal({
  open,
  onClose,
  onCreated,
  initialDate,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  initialDate?: Date;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Novo agendamento" description="Criado como confirmado, por ser um registro manual da equipe.">
      {open && <AppointmentForm key={initialDate?.toISOString() ?? "new"} initialDate={initialDate} onClose={onClose} onCreated={onCreated} />}
    </Modal>
  );
}

function AppointmentForm({ initialDate, onClose, onCreated }: { initialDate?: Date; onClose: () => void; onCreated: () => void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data: servicesData } = useQuery(() => api.get<{ items: Service[] }>(`clinic/${tenant.id}/services`, { active: true }), [tenant.id]);
  const services = servicesData?.items ?? [];
  const [form, setForm] = useState(() => ({
    phone: "",
    patientName: "",
    serviceId: "",
    service: "",
    duration: "60",
    date: toLocalInputValue(initialDate?.toISOString()),
    price: "",
    notes: "",
  }));
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [loading, setLoading] = useState(false);

  function pickService(id: string) {
    const svc = services.find((s) => s.id === id);
    setForm({
      ...form,
      serviceId: id,
      service: svc?.name ?? form.service,
      duration: svc ? String(svc.durationMin) : form.duration,
      price: svc?.priceCents != null ? (svc.priceCents / 100).toFixed(2).replace(".", ",") : form.price,
    });
  }

  async function submit(force: boolean) {
    setError(null);
    setLoading(true);
    try {
      await api.post(`clinic/${tenant.id}/appointments`, {
        phone: form.phone,
        patientName: form.patientName || null,
        service: form.service,
        serviceId: form.serviceId || null,
        date: new Date(form.date).toISOString(),
        durationMin: Number(form.duration) || null,
        priceCents: form.price ? Math.round(Number(form.price.replace(",", ".")) * 100) : null,
        notes: form.notes || null,
        force,
      });
      toast.success("Agendamento criado.");
      onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.code === "slot_unavailable") setConflict(true);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void submit(false);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="WhatsApp do paciente" htmlFor="phone" required>
          <Input id="phone" required inputMode="tel" placeholder="(81) 99999-8888" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </Field>
        <Field label="Nome do paciente" htmlFor="patientName">
          <Input id="patientName" value={form.patientName} onChange={(e) => setForm({ ...form, patientName: e.target.value })} />
        </Field>
        {services.length > 0 && (
          <Field label="Serviço do catálogo" htmlFor="serviceId" hint="Preenche duração e valor automaticamente.">
            <Select id="serviceId" value={form.serviceId} onChange={(e) => pickService(e.target.value)}>
              <option value="">Outro (digitar)</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name} · {s.durationMin} min</option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Procedimento" htmlFor="service" required>
          <Input id="service" required minLength={2} value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value, serviceId: "" })} />
        </Field>
        <Field label="Data e hora" htmlFor="date" required>
          <Input id="date" type="datetime-local" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </Field>
        <Field label="Duração (min)" htmlFor="duration" required>
          <Input id="duration" type="number" min={5} max={600} step={5} required value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} />
        </Field>
        <Field label="Valor (R$)" htmlFor="price" hint="Usado no cálculo de receita.">
          <Input id="price" inputMode="decimal" placeholder="990,00" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
        </Field>
        <Field label="Observações" htmlFor="notes">
          <Input id="notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
      </div>
      {error && (
        <Alert tone={conflict ? "warning" : "danger"}>
          {error}
          {conflict && " Você pode salvar mesmo assim como encaixe."}
        </Alert>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
        {conflict && (
          <Button type="button" variant="secondary" loading={loading} onClick={() => submit(true)}>Salvar como encaixe</Button>
        )}
        <Button type="submit" loading={loading}>Salvar</Button>
      </div>
    </form>
  );
}
