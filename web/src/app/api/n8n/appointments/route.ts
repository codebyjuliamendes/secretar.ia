import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { tenantId, phone, service, date } = body;

    if (!tenantId || !phone || !service || !date) {
      return NextResponse.json({ error: 'Missing required fields (tenantId, phone, service, date)' }, { status: 400 });
    }

    const patient = await prisma.patient.findUnique({
      where: { tenantId_phone: { tenantId, phone } }
    });

    if (!patient) {
      return NextResponse.json({ error: 'Patient not found. Create patient first.' }, { status: 404 });
    }

    const appointment = await prisma.appointment.create({
      data: {
        tenantId,
        patientId: patient.id,
        service,
        date: new Date(date),
        status: "PENDENTE"
      }
    });

    return NextResponse.json(appointment);
  } catch (error) {
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
