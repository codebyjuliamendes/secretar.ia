import { NextResponse } from 'next/server';

// Simulação de Polling SSE / WebSocket Endpoint
// O N8n fará um POST nesta rota quando o classificador bater "HUMANO"
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { tenantId, phone, context } = body;

    if (!tenantId || !phone) {
      return NextResponse.json({ error: 'Missing tenantId or phone' }, { status: 400 });
    }

    // Em produção, isso usaria o Supabase Realtime (.channel('inbox').broadcast(...))
    console.log(`[ALERT] Handoff humano acionado na clínica ${tenantId} para o telefone ${phone}`);
    console.log(`Contexto: ${context}`);

    return NextResponse.json({ success: true, delivered: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to broadcast alert' }, { status: 500 });
  }
}
