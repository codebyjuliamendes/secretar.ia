-- Canal de notificações push do Google Calendar (events.watch) por conexão.
ALTER TABLE "CalendarConnection" ADD COLUMN "channelId" TEXT,
ADD COLUMN "channelResourceId" TEXT,
ADD COLUMN "channelToken" TEXT,
ADD COLUMN "channelExpiresAt" TIMESTAMP(3);

-- CreateIndex
CREATE UNIQUE INDEX "CalendarConnection_channelId_key" ON "CalendarConnection"("channelId");
