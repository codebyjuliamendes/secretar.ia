import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// Simulação de Webhook do Stripe ou Asaas
export async function POST(request: Request) {
  try {
    const payload = await request.json();
    
    // Validar assinatura do webhook (Ignorado para o protótipo)
    const eventType = payload.type;
    const subscriptionId = payload.data?.object?.id || payload.id;
    
    // Se o pagamento falhar ou a assinatura for cancelada
    if (eventType === 'invoice.payment_failed' || eventType === 'customer.subscription.deleted') {
      await prisma.tenant.updateMany({
        where: { subscriptionId },
        data: { status: 'PAST_DUE' } // Bloqueia o acesso ao bot
      });
    }

    // Se o pagamento for bem sucedido
    if (eventType === 'invoice.payment_succeeded') {
      await prisma.tenant.updateMany({
        where: { subscriptionId },
        data: { status: 'ACTIVE' }
      });
    }

    return NextResponse.json({ received: true });
  } catch (error) {
    return NextResponse.json({ error: 'Webhook handler failed' }, { status: 400 });
  }
}
