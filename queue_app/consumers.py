import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AntrianConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.poli_kode = self.scope['url_route']['kwargs']['poli_kode']
        self.group_name = f'antrian_{self.poli_kode}'

        # Gabung ke grup poli
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Keluar dari grup
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # Receive message from WebSocket client (if any)
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'antrian_message',
                'message': data
            }
        )

    # Receive message from group
    async def antrian_message(self, event):
        message = event['message']

        # Kirim pesan ke WebSocket client
        await self.send(text_data=json.dumps(message))
