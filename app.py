# app.py (THE TRULY FINAL, CORRECTED CODE)

import os
import asyncio
import secrets
import traceback
import uvicorn
from urllib.parse import urlparse
from contextlib import asynccontextmanager # <--- THIS IS THE CORRECT IMPORT

import aiohttp
import aiofiles
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from pyrogram.errors import FloodWait
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pyrogram.file_id import FileId
from pyrogram import raw
from pyrogram.session import Session, Auth
import math

# Imports from your other project files
from config import Config
from database import db

# --- Global Variables and Lifespan Manager ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown of the Pyrogram bot.
    """
    print("--- Lifespan event: STARTUP ---")
    await db.connect()
    try:
        print("Starting Pyrogram client in background...")
        await bot.start()
        print(f"Bot [@{bot.me.username}] started successfully.")
        
        print(f"Verifying channel access for {Config.STORAGE_CHANNEL}...")
        await bot.get_chat(Config.STORAGE_CHANNEL)
        print("✅ Channel is accessible.")
        
        try:
            await cleanup_channel(bot)
        except Exception as e:
            print(f"Warning: Initial channel cleanup failed, but continuing startup. Error: {e}")

        multi_clients[0] = bot
        work_loads[0] = 0
        
        print("--- Lifespan startup complete. Bot is running in the background. ---")
    except Exception as e:
        print(f"!!! FATAL ERROR during bot startup in lifespan: {traceback.format_exc()}")
    
    yield
    
    print("--- Lifespan event: SHUTDOWN ---")
    if bot.is_initialized:
        await bot.stop()
    print("--- Lifespan shutdown complete ---")

# Initialize FastAPI app with the lifespan manager
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Initialize Pyrogram Bot Client
bot = Client("SimpleStreamBot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, in_memory=True)

# Global Dictionaries
multi_clients = {}
work_loads = {}
class_cache = {}

# --- (All the other code for handlers, routes, etc. is correct and remains unchanged) ---
def get_readable_file_size(size_in_bytes):
    if not size_in_bytes: return '0B'; power,n=1024,0; p_labels={0:'',1:'K',2:'M',3:'G'}
    while size_in_bytes>=power and n<len(p_labels): size_in_bytes/=power; n+=1
    return f"{size_in_bytes:.2f} {p_labels[n]}B"
def mask_filename(name: str):
    if not name: return "Protected File"; res=["2160p","1080p","720p","480p","360p"]; r_part=""
    for r in res:
        if r in name: r_part=f" {r}"; name=name.replace(r,""); break
    base,ext=os.path.splitext(name); m_base=''.join(c if(i%3==0 and c.isalnum())else'*' for i,c in enumerate(base))
    return f"{m_base}{r_part}{ext}"
@bot.on_message(filters.command("start") & filters.private)
async def start_command(_,m:Message): await m.reply_text(f"👋 **Hello, {m.from_user.first_name}!**\nI'm a file-to-link bot.")
async def handle_file_upload(m:Message,uid:int):
    try:
        sm=await m.copy(Config.STORAGE_CHANNEL); uqid=secrets.token_urlsafe(8); await db.save_link(uqid,sm.id)
        flink=f"{Config.BASE_URL}/show/{uqid}"; btn=InlineKeyboardMarkup([[InlineKeyboardButton("Open Your Link 🔗",url=flink)]])
        await m.reply_text("✅ Link generated!",reply_markup=btn,quote=True)
    except Exception as e: print(f"!!! ERROR: {traceback.format_exc()}"); await m.reply_text("Sorry, something went wrong.")
@bot.on_message(filters.private & (filters.document|filters.video|filters.audio))
async def file_handler(_,m:Message): await handle_file_upload(m,m.from_user.id)
@bot.on_message(filters.command("url") & filters.private & filters.user(Config.OWNER_ID))
async def url_upload_handler(_,m:Message):
    if len(m.command)<2: await m.reply_text("Usage: `/url <link>`"); return
    url=m.command[1]; fname=os.path.basename(urlparse(url).path) or f"file_{int(asyncio.get_running_loop().time())}"; smsg=await m.reply_text("Processing...")
    fpath=os.path.join('downloads',fname)
    if not os.path.exists('downloads'): os.makedirs('downloads')
    try:
        async with aiohttp.ClientSession() as s,s.get(url,timeout=None) as r:
            if r.status!=200: await smsg.edit_text(f"Download failed: {r.status}"); return
            async with aiofiles.open(fpath,'wb') as f:
                async for c in r.content.iter_chunked(1024*1024): await f.write(c)
    except Exception as e: await smsg.edit_text(f"Error: {e}");
    if os.path.exists(fpath): os.remove(fpath); return
    try: sm=await bot.send_document(Config.STORAGE_CHANNEL,fpath); await handle_file_upload(sm,m.from_user.id); await smsg.delete()
    finally:
        if os.path.exists(fpath): os.remove(fpath)
@bot.on_chat_member_updated(filters.chat(Config.STORAGE_CHANNEL))
async def simple_gatekeeper(c:Client,m_update:ChatMemberUpdated):
    try:
        if(m_update.new_chat_member and m_update.new_chat_member.status==enums.ChatMemberStatus.MEMBER):
            u=m_update.new_chat_member.user
            if u.id==Config.OWNER_ID or u.is_self: return
            print(f"Gatekeeper: Kicking {u.id}"); await c.ban_chat_member(Config.STORAGE_CHANNEL,u.id); await c.unban_chat_member(Config.STORAGE_CHANNEL,u.id)
    except Exception as e: print(f"Gatekeeper Error: {e}")
async def cleanup_channel(c:Client):
    print("Gatekeeper: Running cleanup..."); allowed={Config.OWNER_ID,c.me.id}
    try:
        async for m in c.get_chat_members(Config.STORAGE_CHANNEL):
            if m.user.id in allowed: continue
            if m.status in [enums.ChatMemberStatus.ADMINISTRATOR,enums.ChatMemberStatus.OWNER]: continue
            try: print(f"Cleanup: Kicking {m.user.id}"); await c.ban_chat_member(Config.STORAGE_CHANNEL,m.user.id); await asyncio.sleep(1)
            except FloodWait as e: await asyncio.sleep(e.value)
            except Exception as e: print(f"Cleanup Error: {e}")
    except Exception as e: print(f"Cleanup Error: {e}")
class ByteStreamer:
    def __init__(self,c:Client):self.client=c
    @staticmethod
    async def get_location(f:FileId): return raw.types.InputDocumentFileLocation(id=f.media_id,access_hash=f.access_hash,file_reference=f.file_reference,thumb_size=f.thumbnail_size)
    async def yield_file(self,f:FileId,i:int,o:int,fc:int,lc:int,pc:int,cs:int):
        c=self.client;work_loads[i]+=1;ms=c.media_sessions.get(f.dc_id)
        if ms is None:
            if f.dc_id!=await c.storage.dc_id():
                ak=await Auth(c,f.dc_id,await c.storage.test_mode()).create();ms=Session(c,f.dc_id,ak,await c.storage.test_mode(),is_media=True);await ms.start();ea=await c.invoke(raw.functions.auth.ExportAuthorization(dc_id=f.dc_id));await ms.invoke(raw.functions.auth.ImportAuthorization(id=ea.id,bytes=ea.bytes))
            else:ms=c.session
            c.media_sessions[f.dc_id]=ms
        loc=await self.get_location(f);cp=1
        try:
            while cp<=pc:
                r=await ms.invoke(raw.functions.upload.GetFile(location=loc,offset=o,limit=cs),retries=0)
                if isinstance(r,raw.types.upload.File):
                    chk=r.bytes
                    if not chk:break
                    if pc==1:yield chk[fc:lc]
                    elif cp==1:yield chk[fc:]
                    elif cp==pc:yield chk[:lc]
                    else:yield chk
                    cp+=1;o+=cs
                else:break
        finally:work_loads[i]-=1
@app.get("/show/{uid}",response_class=HTMLResponse)
async def show_page(r:Request,uid:str):
    mid=await db.get_link(uid)
    if not mid:raise HTTPException(404)
    mb=multi_clients.get(0);
    if not mb:raise HTTPException(503)
    fmsg=await mb.get_messages(Config.STORAGE_CHANNEL,mid);m=fmsg.document or fmsg.video or fmsg.audio
    if not m:raise HTTPException(404)
    oname=m.file_name or "file";sname="".join(c for c in oname if c.isalnum() or c in (' ','.','_','-')).rstrip()
    ctx={"request":r,"file_name":mask_filename(oname),"file_size":get_readable_file_size(m.file_size),"is_media":(m.mime_type or "").startswith(("v","a")),"direct_dl_link":f"{Config.BASE_URL}/dl/{mid}/{sname}","mx_player_link":f"intent:{Config.BASE_URL}/dl/{mid}/{sname}#Intent;action=android.intent.action.VIEW;type={m.mime_type or 'v/*'};end","vlc_player_link":f"vlc://{Config.BASE_URL}/dl/{mid}/{sname}"}
    return templates.TemplateResponse("show.html",ctx)
@app.get("/dl/{mid}/{fname}")
async def stream_media(r:Request,mid:int,fname:str):
    i=min(work_loads,key=work_loads.get,default=0);c=multi_clients.get(i)
    if not c:raise HTTPException(503)
    tc=class_cache.get(c) or ByteStreamer(c);class_cache[c]=tc
    try:
        msg=await c.get_messages(Config.STORAGE_CHANNEL,mid);m=msg.document or msg.video or msg.audio
        if not m or msg.empty:raise FileNotFoundError
        fid=FileId.decode(m.file_id);fsize=m.file_size;rh=r.headers.get("Range",0);fb,ub=0,fsize-1
        if rh:fbs,ubs=rh.replace("bytes=","").split("-");fb=int(fbs)
        if 'ubs' in locals() and ubs:ub=int(ubs)
        if(ub>=fsize)or(fb<0):raise HTTPException(416)
        rl=ub-fb+1;cs=1024*1024;off=(fb//cs)*cs;fc=fb-off;lc=(ub%cs)+1;pc=math.ceil(rl/cs)
        body=tc.yield_file(fid,i,off,fc,lc,pc,cs);sc=206 if rh else 200
        hdrs={"Content-Type":m.mime_type or "application/octet-stream","Accept-Ranges":"bytes","Content-Disposition":f'inline; filename="{m.file_name}"',"Content-Length":str(rl)}
        if rh:hdrs["Content-Range"]=f"bytes {fb}-{ub}/{fsize}"
        return StreamingResponse(body,status_code=sc,headers=hdrs)
    except FileNotFoundError:raise HTTPException(404)
    except Exception:print(traceback.format_exc());raise HTTPException(500)
# ...

# --- Main Execution Block ---

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="#12 exporting cache to client directory
#12 preparing build cache for export
#12 writing cache image manifest sha256:d8c6b2401666e850b1d3d63c437f1983050b178c187e076717596a70a000000a 0.0s done
#12 DONE 2.2s
Pushing image to registry...
Upload succeeded
==> Deploying...
INFO:     Started server process [1]
INFO:     Waiting for application startup.
--- Lifespan event: STARTUP ---
Connecting to the database...
✅ Database connection established.
Starting Pyrogram client in background...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
Bot [@SharingBoxBot] started successfully.
Verifying channel access for @hkdqyvb...
✅ Channel is accessible.
Gatekeeper: Running cleanup...
Gatekeeper: Initial channel cleanup complete.
--- Lifespan startup complete. Bot is running in the background. ---
==> Your service is live 🎉
==> 
==> ///////////////////////////////////////////////////////////
==> 
==> Available at your primary URL https://sharingbox.onrender.com
==> 
==> ///////////////////////////////////////////////////////////
INFO:     10.223.25.152:0 - "GET / HTTP/1.1" 404 Not Found

0.0.0.0", port=port)
