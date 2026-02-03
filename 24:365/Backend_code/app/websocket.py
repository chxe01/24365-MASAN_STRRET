import asyncio
import websockets

async def handler(websocket, path):
    print("New client connected.")

    ping_task = asyncio.create_task(send_ping(websocket))
    
    try:
        async for message in websocket:
            print(f"Received: {message}")
            await websocket.send(f"Server received: {message}")
            
    finally:
        print("Client disconnected.")

start_server = websockets.serve(handler, "0.0.0.0", 8765)