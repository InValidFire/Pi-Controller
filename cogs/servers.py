from discord.ext import commands, tasks
from cogs.core import is_admin
import core.common as common
import core.embed as ebed
import shlex
import zipfile
import random
import discord
import requests
import asyncio
import os


async def dircheck(directory) -> bool:
    print("Running dircheck")
    return os.path.exists(directory)


async def load_args(data: dict) -> dict:
    """Load args for the given dict. Replaces placeholders with their actual values"""
    print("Loading Args for dict: {}".format(str(data)))
    newdict = {}
    argdict = data['args']
    for key in data.keys():
        if key == 'args':
            continue
        item = data[key]
        for argkey in argdict.keys():
            if "#{}#".format(argkey) in item:
                item = item.replace('#{}#'.format(argkey), argdict[argkey])
                print("Loaded arg '{}' for item '{}', new value: {}".format(argkey, key, item))
        newdict[key] = item
    print(newdict)
    return newdict


async def load_file_args(data: dict) -> dict:
    """Recursively load arguments from a dictionary."""
    for key in data:
        if key == "args":
            print("Found args key for data: {}".format(key))
            data = await load_args(data)
        elif isinstance(data[key], dict):
            print("Found dict for key: {}".format(key))
            data[key] = await load_file_args(data[key])
        elif isinstance(data[key], list):
            print("Found list for key: {}".format(key))
            for item in data[key]:
                if isinstance(item, dict):
                    data[key][data[key].index(item)] = await load_file_args(item)
    return data


async def download_file(url, save_file):  # move to thread
    """Download the given server and initialize setup."""
    print("Running download_file")
    r = requests.get(url, stream=True)
    with open(save_file, "wb") as fd:
        i = 0
        for chunk in r.iter_content(chunk_size=512):
            if chunk:
                i += 1
                fd.write(chunk)


async def makedir(dir_name: str) -> str:
    """Creates directory if needed, returns directory path."""
    print("Running makedir")
    if await dircheck(dir_name) is False:
        os.makedirs(dir_name)
        print("Made directory '{}'".format(dir_name))
    else:
        print("Directory '{}' already exists".format(dir_name))
    return dir_name


async def asyncio_subprocess(program):
    """Runs a async compatible subprocess, returning the created process."""
    process = await asyncio.create_subprocess_exec(*program,
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stdin=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    return process


async def load_embed(meta: dict) -> discord.Embed:
    """Common embed builder used to create embeds used with server messages."""
    if "embed_color" in meta:  # load color
        if isinstance(meta['embed_color'], str):
            embed = discord.Embed(color=ebed.hex_to_rgb(meta['embed_color']))
        elif isinstance(meta['embed_color'], list):  # TODO: Add error handling for JSON format.
            color = random.choice(meta['embed_color'])
            embed = discord.Embed(color=ebed.hex_to_rgb(color))
        else:
            embed = discord.Embed(color=ebed.randomrgb())
    else:
        embed = discord.Embed(color=ebed.randomrgb())
    if "desc" in meta and "icon" in meta:  # load footer
        embed.set_footer(icon_url=meta['icon'], text="{name} - {desc}".format(name=meta['name'], desc=meta['desc']))
    elif "desc" in meta:
        embed.set_footer(text="{name} - {desc}".format(name=meta['name'], desc=meta['desc']))
    elif "icon" in meta:
        embed.set_footer(icon_url=meta['icon'], text=meta['name'])
    return embed


class Servers(commands.Cog):
    """Cog focused for controlling 3rd-Party Servers through JSON data."""
    def __init__(self, bot):
        self.bot = bot
        self.server_data = None
        self.current_console = None
        self.current_process = None
        self.current_dir = None
        self.main_dir = os.getcwd()
        self.server_cleanup.start()

    async def download(self, server_data: dict):
        """Initiates download functions for the given server."""
        print("Running download")
        main_dir = os.getcwd()
        server_dir = await makedir(server_data['meta']['directories']['main'])
        os.chdir(server_dir)
        file_dir = server_data['download']['file']
        link = server_data['download']['link']
        await download_file(link, file_dir)
        await self.run_command("setup")
        os.chdir(main_dir)

    @tasks.loop(seconds=1)
    async def server_cleanup(self):
        """Resets server-specific values after a server has terminated for any reason."""
        if self.current_process is not None:
            if self.current_process.returncode is not None and hasattr(self.console_read, "finished"):
                self.server_data = None
                self.current_process = None
                self.current_console = None
                await self.bot.change_presence(activity=None)
                os.chdir(common.getbotdir())
                print("The running server has been terminated, resetting values.")

    @tasks.loop(seconds=1)
    async def console_read(self, channel_id):
        """Sends data from process output to the specified discord channel."""
        channel = discord.utils.get(self.bot.get_all_channels(), id=channel_id)
        if self.current_process is not None:
            if self.current_process.stdout.at_eof() is not True:
                print("Waiting for console output...")
                data = await asyncio.wait_for(self.current_process.stdout.readline(), 3)
                reply = data.decode().strip()
                await channel.send(reply)
                print("Sent: {}".format(reply))
            else:
                print("Nothing to read.")
                self.console_read.finished = True  # keeps the server_cleanup from running until all messages are sent.
        else:
            print("Stopping console_read task, no server running.")
            self.console_read.stop()

    async def console_write(self, data):
        """Writes the given data to the process stdin."""
        if self.current_process is not None:
            print("Writing '{}' to console".format(data))
            data += "\n"
            data = data.encode()
            self.current_process.stdin.write(data)
            await self.current_process.stdin.drain()
            print("Finished console_write")

    def extract(self, path, dest):
        with zipfile.ZipFile(path, 'r') as file:
            file.extractall(os.path.join(common.getbotdir(), self.server_data['meta']['directories'][dest]))

    async def asyncio_extract(self, path, dest):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.extract, path, dest)

    async def run_command(self, command: str):  # TODO: Move each case into its' own function for handling.
        """Process the given command found in serverdata."""
        statustypes = {"playing": discord.ActivityType.playing,
                       "watching": discord.ActivityType.watching,
                       "streaming": discord.ActivityType.streaming,
                       "listening": discord.ActivityType.listening}
        cmd = self.server_data["commands"][command]
        i = 0
        m = len(cmd)
        print("Running command: {}".format(command))
        for step in cmd:
            i += 1  # step counter.
            print("Running step {} of {}".format(i, m))
            if 'file' in step.keys():
                print("Running file function for step: {}".format(step))
                if 'create' in step['file'].keys():
                    await common.makefile(os.path.join(self.server_data['meta']['directories']['main'],
                                                       step['file']['create']['name']),
                                          step['file']['create']['data'])
                if 'extract' in step['file'].keys():
                    await self.asyncio_extract(step['file']['extract']['name'], step['file']['extract']['folder'])
            elif 'presence' in step.keys():
                if step['presence']['type'] is not None:
                    activity = discord.Activity(name=step['presence']['status'],
                                                type=statustypes[step['presence']['type']])
                else:
                    activity = None
                await self.bot.change_presence(activity=activity)
            elif 'shell' in step.keys():
                self.current_process = await asyncio_subprocess(shlex.split(step['shell']))
            elif 'channel' in step.keys():
                print("Found 'channel' key")
                if step['channel']['type'] == 'console':
                    print("Found 'console' key")
                    self.current_console = step['channel']['id']
                    self.console_read.start(step['channel']['id'])
            elif 'console' in step.keys():
                print("Sending command '{}' to server console.".format(step['console']))
                await self.console_write(step['console'])
            elif 'command' in step.keys():
                print("Running command {}.".format(step['command']))
                await self.run_command(step['command'])
            elif 'directory' in step.keys():
                print("Changing directory to: {}".format(step['directory']))
                os.chdir(os.path.join(common.getbotdir(), self.server_data['meta']['directories']['main'],
                                      self.server_data['meta']['directories'][step['directory']]))
            elif 'process' in step.keys():
                if step['process'] == 'kill':
                    print("Killing current process.")
                    self.current_process.kill()
                    await self.current_process.communicate()

    @commands.group(aliases=["servers"])
    async def server(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid command.")

    @server.command(pass_context=True)
    @commands.check(is_admin)
    async def start(self, ctx, server_name: str):
        """Start a server"""
        if os.path.exists(os.path.join(common.getbotdir(), "data", "servers", "{}.json".format(server_name))):
            self.server_data = await load_file_args(await common.loadjson("data/servers/{}.json".format(server_name)))
            print("Loaded '{}' server data.".format(server_name))
            if await dircheck(self.server_data['meta']['directories']['main']):
                os.chdir(self.server_data['meta']['directories']['main'])  # so shell commands run in their directories
                await self.run_command("start")
                embed = await load_embed(self.server_data['meta'])
                embed.description = "Starting server."
                await ctx.send(embed=embed)
            else:  # not downloaded yet
                embed = await load_embed(self.server_data['meta'])
                embed.description = "Server directory not found, starting download."
                await ctx.send(embed=embed)
                embed = await load_embed(self.server_data['meta'])
                embed.description = "Download finished, run again to start the server."
                await self.download(self.server_data)
                await ctx.send(embed=embed)
        else:
            await ctx.send("No server by '{}' found".format(server_name))

    @server.command(pass_context=True)
    @commands.check(is_admin)
    async def stop(self, ctx):
        embed = await load_embed(self.server_data['meta'])
        embed.description = "Stopping server."
        await ctx.send(embed=embed)
        await self.run_command("stop")

    @server.command(pass_context=True)
    @commands.check(is_admin)
    async def run(self, ctx, command):
        if self.server_data is None:
            embed = discord.Embed(color=ebed.randomrgb())
            embed.description = "No server running."
            await ctx.send(embed=embed)
        else:
            embed = await load_embed(self.server_data['meta'])
            if command == "start" or command == "setup":
                embed.description = "System command. Unable to run through this method."
                await ctx.send(embed=embed)
            elif command in self.server_data['commands']:
                embed.description = "Running command: {}".format(command)
                await ctx.send(embed=embed)
                await self.run_command(command)
            else:
                embed.description = "No command '{command}' found.".format(command=command)
                await ctx.send(embed=embed)

    @server.group(pass_context=True)
    @commands.check(is_admin)
    async def data(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid command.")

    @data.command(pass_context=True)
    @commands.check(is_admin)
    async def get(self, ctx, file):
        """Receive raw JSON serverdata from the loaded file."""
        await ctx.author.send(file=discord.File(os.path.join(common.getbotdir(),
                                                             "data",
                                                             "servers",
                                                             "{}.json".format(file))))

    @server.command(pass_context=True)
    @commands.check(is_admin)
    async def list(self, ctx):
        """List all servers available to launch."""
        color = ebed.randomrgb()
        embed = discord.Embed(title="Servers Listed",
                              color=color)
        count = 0
        msg = ""
        for file in os.listdir(os.path.join(common.getbotdir(), "data", "servers")):
            count += 1
            msg += "\n**-** {}".format(os.path.splitext(file)[0])
        embed.add_field(name="{} available".format(count), value=msg, inline=False)
        embed.set_footer(text=ebed.rgb_to_hex(color.to_rgb()))
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, msg):
        if await is_admin(msg) and self.current_console is not None:
            if msg.channel.id == self.current_console:
                await self.console_write(msg.content)


def setup(bot):
    bot.add_cog(Servers(bot))
