from typing import List

import aiohttp
import asyncio
import toml
import json
import time
from dataclasses import dataclass
import logging

logging.basicConfig(format="[%(asctime)s — %(name)s — %(levelname)s] %(message)s", level=logging.DEBUG)

class AuthenticationError(Exception):
    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return f"AuthenticationError({self.reason!r})"

    __str__ = __repr__

@dataclass
class Door:
    name: str
    id: str

    @staticmethod
    def from_obj(obj):
        return Door(
            name=obj["name"],
            id=obj["id"],
        )

@dataclass
class Secrets:
    login_username: str
    login_password: str
    doors: List[Door]

    def __str__(self):
        return f"Secrets(login_username={self.login_username!r}, login_password=[redacted], doors={self.doors})"
    __repr__ = __str__

    @staticmethod
    def from_secrets_obj(obj):
        return Secrets(
            login_username=obj["csb-login"]["username"],
            login_password=obj["csb-login"]["password"],
            doors=[Door.from_obj(door_obj) for door_obj in obj["doors"]],
        )

    @staticmethod
    def from_toml_file(secrets_path):
        with open(secrets_path, "r") as secrets:
            return Secrets.from_secrets_obj(toml.load(secrets))

class DoorControl:
    def __init__(self, secrets: Secrets):
        self.secrets = secrets
        self.sess = aiohttp.ClientSession()
        self.lock = asyncio.Lock()
        self.log = logging.getLogger("DoorControl")

    async def __aenter__(self):
        self.log.debug("Initializing (__aenter__)")
        await self.sess.__aenter__()
        await self.relogin()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.log.debug("Terminating (__aexit__)")
        await self.sess.__aexit__(exc_type, exc, tb)

    async def relogin(self):
        self.log.info(f"Getting new credentials")

        # create a new session
        login_sess = aiohttp.ClientSession()
        await login_sess.__aenter__()

        self.log.debug(f"Started login session")
        await login_csb(login_sess, self.secrets)
        self.log.debug(f"Got CSB credentials")
        await login_aptus(login_sess)
        self.log.debug(f"Got aptus credentials")

        # swap them out
        old_sess = self.sess
        self.sess = login_sess

        # cleanup old_sess
        await old_sess.__aexit__(None, None, None)
        self.log.info(f"Got new credentials")

    async def unlock_door(self, door: Door):
        self.log.info(f"Unlocking door {door}")

        # This should always work, and only fetch a new session when necessary.
        # However, this might break. YMMV
        try:
            await unlock_door(self.sess, door)
        except AuthenticationError:
            self.log.info("Session expired. Logging in again")
            await self.relogin()
            await unlock_door(self.sess, door)

async def login_csb(sess: aiohttp.ClientSession, secrets: Secrets):
    await sess.post(
        "https://www.chalmersstudentbostader.se/wp-login.php",
        data={
            "log": secrets.login_username,
            "pwd": secrets.login_password,
            "redirect_to": "https://www.chalmersstudentbostader.se/mina-sidor/",
        },
    )
    if "Fast2User_ssoId" not in [c.key for c in sess.cookie_jar]:
        raise AuthenticationError("wp-login.php failed")

async def login_aptus(sess: aiohttp.ClientSession):
    data = await sess.get(
        "https://www.chalmersstudentbostader.se/widgets/",
        params={
            "callback": "mjau",
            "widgets[]": "aptuslogin@APTUSPORT",
        },
    )
    if data.status != 200:
        raise AuthenticationError("aptus login url @ /widgets/")

    json_data = json.loads((await data.text())[5:-2])
    try:
        aptus_url = json_data["data"]["aptuslogin@APTUSPORT"]["objekt"][0]["aptusUrl"]
    except ValueError as e:
        raise AuthenticationError("aptus login url @ /widgets/")

    resp = await sess.get(aptus_url) # this sets login-cookies
    if resp.status != 200:
        raise AuthenticationError("aptus login url")

async def unlock_door(sess: aiohttp.ClientSession, door: Door):
    resp = await sess.get(
        f"https://apt-www.chalmersstudentbostader.se/AptusPortal/Lock/UnlockEntryDoor/{door.id}",
    )
    if resp.status != 200:
        raise AuthenticationError("/UnlockEntryDoor/")

if __name__ == "__main__":
    async def main():
        secrets = Secrets.from_toml_file("./secrets.toml")
        async with DoorControl(secrets) as dc:
            await dc.unlock_door(secrets.doors[0])

    asyncio.run(main())
