import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { tenantId, phone, name } = body;

    if (!tenantId || !phone) {
      return NextResponse.json({ error: 'tenantId and phone are required' }, { status: 400 });
    }

    let patient = await prisma.patient.findUnique({
      where: {
        tenantId_phone: {
          tenantId,
          phone
        }
      }
    });

    if (!patient) {
      patient = await prisma.patient.create({
        data: {
          tenantId,
          phone,
          name: name || 'Desconhecido'
        }
      });
    }

    return NextResponse.json({ patient, isNew: !patient.updatedAt });
  } catch (error) {
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
