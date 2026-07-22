import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// Rota de CRON. Chamada pelo Vercel Cron
export async function GET(request: Request) {
  try {
    const authorization = request.headers.get('Authorization');
    // Basic API Key validation
    if (authorization !== `Bearer ${process.env.CRON_SECRET}`) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const fiveMonthsAgo = new Date();
    fiveMonthsAgo.setMonth(fiveMonthsAgo.getMonth() - 5);
    
    const startOfDay = new Date(fiveMonthsAgo.setHours(0, 0, 0, 0));
    const endOfDay = new Date(fiveMonthsAgo.setHours(23, 59, 59, 999));

    const targets = await prisma.appointment.findMany({
      where: {
        date: {
          gte: startOfDay,
          lte: endOfDay
        },
        service: {
          contains: 'Toxina' 
        },
        status: 'REALIZADO' 
      },
      include: {
        patient: true,
        tenant: true
      }
    });

    // Aqui acionaria o N8n enviando a lista de clientes para disparar o WhatsApp
    return NextResponse.json({ 
      success: true, 
      messagesSent: targets.length,
      targets 
    });

  } catch (error) {
    return NextResponse.json({ error: 'Marketing cron failed' }, { status: 500 });
  }
}
