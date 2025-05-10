import discord
from discord.ext import commands
import asyncio
import yt_dlp  

# Cola de reproducción global
song_queue = []
voice_client = None  

# Opciones para yt-dlp
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(title)s.%(ext)s',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'audioquality': '0', 
}

# Crear instancia de yt-dlp
ydl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Crear instancia del bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Función para obtener la fuente de audio usando yt-dlp
async def get_audio_source(url):
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        audio_url = data.get('url')
        title = data.get('title')
        duration = data.get('duration')
        return audio_url, title, duration
    except Exception as e:
        print(f"Error al obtener la fuente de audio con yt-dlp: {e}")
        return None, None, None

async def connect_to_voice(ctx):
    global voice_client
    channel = ctx.author.voice.channel
    if not channel:
        await ctx.send("¡Únete a un canal de voz primero!")
        return None
    if voice_client is None or not voice_client.is_connected():
        try:
            voice_client = await channel.connect()
        except discord.ClientException:
            await ctx.send("Ya estoy conectado a un canal de voz.")
            return voice_client
        except discord.opus.OpusNotLoaded:
            await ctx.send("La librería opus no está cargada. Asegúrate de tener libopus instalado.")
            return None
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)
    return voice_client

async def play_next(ctx):
    global song_queue
    global voice_client
    print(f"PLAY_NEXT: Cola size: {len(song_queue)}, is_playing: {voice_client.is_playing() if voice_client else None}")
    if song_queue:
        audio_url, title, duration = song_queue.pop(0)
        print(f"PLAY_NEXT: Reproduciendo ahora: {title} ({audio_url})")
        if voice_client is None or not voice_client.is_connected():
            voice_client = await connect_to_voice(ctx)
            if voice_client is None:
                return

        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -b:a 192k -bufsize 192k'
        }
        
        try:
            source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS, executable='ffmpeg')
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            await ctx.send(f"Reproduciendo: {title}")
            
            # Esperar a que termine la canción
            if duration:
                await asyncio.sleep(duration + 1)  # Añadimos 1 segundo extra para asegurar que termine
        except Exception as e:
            print(f"Error al reproducir: {e}")
            await ctx.send(f"Error al reproducir {title}. Intentando la siguiente canción...")
            await play_next(ctx)
    elif voice_client and voice_client.is_connected():
        await ctx.send("La cola de reproducción ha terminado. ")
        await asyncio.sleep(5)
        if not song_queue and len(voice_client.channel.members) == 1:
            await voice_client.disconnect()
            voice_client = None

@bot.command(name="play")
async def play_command(ctx, *, url: str):
    global song_queue
    global voice_client
    print(f"PLAY_COMMAND: Recibida URL: {url}")
    audio_url, title, duration = await get_audio_source(url)
    if audio_url:
        song_queue.append((audio_url, title, duration))
        await ctx.send(f"{title} ha sido añadida a la cola. ")
        print(f"PLAY_COMMAND: Añadida a la cola: {title}")
        if voice_client is None or not voice_client.is_playing():
            await play_next(ctx)
    else:
        await ctx.send("No se pudo obtener la fuente de audio.")
        print(f"PLAY_COMMAND: No se pudo obtener la fuente de audio para: {url}")



async def check_vc_members(ctx):
    global voice_client
    if voice_client and voice_client.is_connected():
        if len(voice_client.channel.members) == 1:
            await voice_client.disconnect()
            voice_client = None
            await ctx.send("¡Me desconecté del canal de voz porque no hay más usuarios!")

# Comando para saltar la canción actual
@bot.command()
async def skip(ctx):
    global voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("¡Canción saltada!")
        await play_next(ctx)
    else:
        await ctx.send("No hay ninguna canción reproduciéndose para saltar.")

# Comando para ver la cola de reproducción
@bot.command()
async def queue(ctx):
    global song_queue
    if not song_queue:
        await ctx.send("La cola está vacía.")
        return

    song_list = "\n".join([f"{i+1}. {song[1]}" for i, song in enumerate(song_queue)])
    await ctx.send(f"Lista de reproducción:\n{song_list}")

# Comando para ver la canción que se está reproduciendo actualmente
@bot.command()
async def nowplaying(ctx):
    global voice_client
    if voice_client and voice_client.is_playing():
        current_song = song_queue[0] if song_queue else None
        if current_song:
            await ctx.send(f"reproducuendo: {current_song[1]}")
        else:
            await ctx.send("No hay ninguna canción en reproducción.")
    else:
        await ctx.send("No hay ninguna canción reproduciéndose.")

@bot.command()
async def stop(ctx):
    global voice_client
    global song_queue
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        song_queue = []  # Limpiar la cola al detener
        await ctx.send("¡Reproducción detenida y la cola ha sido limpiada!")
    else:
        await ctx.send("No hay nada reproduciéndose.")

@bot.command()
async def leave(ctx):
    global voice_client
    global song_queue
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        voice_client = None
        song_queue = []  # Limpiar la cola al desconectar
        await ctx.send("¡Me desconecté del canal de voz y la cola ha sido limpiada!")
    else:
        await ctx.send("No estoy conectado a ningún canal de voz.")

# Evento cuando el bot se conecta correctamente
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Tomando Lechita"), status=discord.Status.online)

# Evento para procesar mensajes y verificar menciones
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mention in message.content:
        parts = message.content.split()
        if len(parts) > 1:
            command = parts[1].lower()
            if command == 'pollo' and len(parts) > 2:
                url = parts[2]
                await play_command(message, url=url)
                return
            elif command == 'play' and len(parts) > 2:
                url = parts[2]
                await play_command(message, url=url)

    await bot.process_commands(message)

# Ejecutar el bot - el token siempre debe de estar en un .env por ahora que sea aca, pero no es seguro
bot.run('Token Discord')