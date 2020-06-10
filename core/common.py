import asyncio
import aiofiles
import aiohttp
import zipfile
import json
import sys
import os


botdir = ""


def setbotdir() -> str:
    global botdir
    botdir = os.path.dirname(os.path.realpath(sys.argv[0]))
    print("Bot directory has been set: {}".format(botdir))
    return botdir


def getbotdir() -> str:
    """Returns the root directory of the bot as a string."""
    global botdir
    return botdir


async def download_file(url, save_file: str, chunk_size=512):  # move to thread
    """Download the given server and initialize setup. Non-Blocking, requires await."""
    print("Running download_file")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            async with aiofiles.open(save_file, "wb") as fd:
                while True:
                    chunk = await resp.content.read(chunk_size)
                    if not chunk:
                        break
                    await fd.write(chunk)


async def read_file(path, mode):
    async with aiofiles.open(path, mode) as fp:
        data = await fp.read()
        return data


def extract(path, dest):
    with zipfile.ZipFile(path, 'r') as file:
        file.extractall(dest)


async def asyncio_extract(path, dest):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, extract, path, dest)


def dircheck(directory) -> bool:
    print("Running dircheck")
    return os.path.exists(directory)


async def makefile(filename: str, data: any):
    """Make a file with the given data written. Non-Blocking, requires await."""
    root = getbotdir()
    path = os.path.join(root, filename)
    async with aiofiles.open(path, mode="w+") as file:
        await file.write(data)


def makedir(dir_name: str) -> str:
    """Creates directory if needed, returns directory path."""
    print("Running makedir")
    if dircheck(dir_name) is False:
        os.makedirs(dir_name)
        print("Made directory '{}'".format(dir_name))
    else:
        print("Directory '{}' already exists".format(dir_name))
    return dir_name


async def loadjson(filename: str) -> dict:
    """Load json file, return the data. Non-Blocking, requires await."""
    root = getbotdir()
    path = os.path.join(root, filename)
    async with aiofiles.open(path, "r") as file:
        content = await file.read()
    data = json.loads(content)
    return data


async def dumpjson(data: dict, filename: str):
    """Save data dictionary to the given file. Non-Blocking, requires await."""
    async with aiofiles.open(filename, "w+") as file:
        content = json.dumps(data, indent=4, sort_keys=True)
        await file.write(content)
