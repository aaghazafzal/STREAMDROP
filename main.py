# main.py
import asyncio
import uvicorn
from bot import bot, initialize_clients
from webserver import app

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def run_bot():
    await bot.start()
    print("Main bot started.")
    await initialize_clients(bot)
    print("All clients initialized. Bot is now fully running.")
    await bot.idle()
    print("Bot is stopping.")

async def main():
    print("Starting application...")
    # Dono ko ek saath run karo
    server_task = asyncio.create_task(run_server())
    bot_task = asyncio.create_task(run_bot())
    
    await asyncio.gather(server_task, bot_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
