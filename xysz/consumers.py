from channels.generic.websocket import AsyncWebsocketConsumer
import json

class MarketConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": "You are now connected!"
        }))

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message
        }))