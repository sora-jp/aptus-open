from aiohttp import web
import asyncio
import argparse
import logging
from aptus_open.lib import DoorControl, Secrets, AuthenticationError

log = logging.getLogger("web")

def routes(dc: DoorControl):
    routes = web.RouteTableDef()

    @routes.post("/unlock-door/{door_id}")
    async def unlock_door(req: web.Request):
        door_id = req.match_info["door_id"]
        matching_doors = [door for door in dc.secrets.doors if door.name == door_id]
        if len(matching_doors) == 0:
            log.error(f"Request for unknown door {door_id}")
            return web.Response(text="no such door", status=404)
        if len(matching_doors) > 1:
            log.error(f"Multiple doors matching {door_id!r}: {matching_doors!r}")
            return web.Response(text="many doors matching id", status=500)

        door = matching_doors[0]
        log.info(f"Opening {door!r}")

        try:
            await dc.unlock_door(door)

            return web.Response(text="success")
        except AuthenticationError as e:
            log.error(f"Failed to open door: {e!r}")
            return web.Response(text="fail", status=500)

    return routes

async def main():
    parser = argparse.ArgumentParser(prog="aptus-open")
    parser.add_argument("-p", "--port", type=int, default=2138, help="port to listen on")
    parser.add_argument("-s", "--secrets-file", type=str, required=True, help="path to secrets toml-file")

    env = parser.parse_args()

    secrets = Secrets.from_toml_file(env.secrets_file)

    async with DoorControl(secrets) as dc:
        app = web.Application()
        app.add_routes(routes(dc))
        runner = web.AppRunner(app)
        await runner.setup()
        log.info(f"Listening on port {env.port}")
        site = web.TCPSite(runner, "localhost", env.port)
        await site.start()

        # wait forever
        while True:
            await asyncio.sleep(1)

def sync_main():
    asyncio.run(main())
