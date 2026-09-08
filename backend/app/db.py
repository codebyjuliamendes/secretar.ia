"""Instância única do Prisma Client."""

from generated_prisma import Prisma

db = Prisma(auto_register=True)
