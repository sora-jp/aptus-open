from typing import List

import requests
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
        self.sess = requests.sessions.Session()
        self.log = logging.getLogger("DoorControl")

    def __enter__(self):
        self.log.debug("Initializing (__enter__)")
        self.sess = self.sess.__enter__()
        self.relogin()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.log.debug("Terminating (__exit__)")
        self.sess.__exit__(exc_type, exc, tb)

    def relogin(self):
        self.log.info(f"Getting new credentials")

        # create a new session
        login_sess = requests.sessions.Session()
        login_sess.__enter__()

        self.log.debug(f"Started login session")
        login_csb(login_sess, self.secrets)
        self.log.debug(f"Got CSB credentials")
        login_aptus(login_sess)
        self.log.debug(f"Got aptus credentials")

        # swap them out
        old_sess = self.sess
        self.sess = login_sess

        # cleanup old_sess
        old_sess.__exit__(None, None, None)
        self.log.info(f"Got new credentials")

    def unlock_door(self, door: Door):
        self.log.info(f"Unlocking door {door}")

        # This should always work, and only fetch a new session when necessary.
        # However, this might break. YMMV
        try:
            unlock_door(self.sess, door)
        except AuthenticationError:
            self.log.info("Session expired. Logging in again")
            self.relogin()
            unlock_door(self.sess, door)

def login_csb(sess: requests.sessions.Session, secrets: Secrets):
    sess.post(
        "https://www.chalmersstudentbostader.se/wp-login.php",
        data={
            "log": secrets.login_username,
            "pwd": secrets.login_password,
            "redirect_to": "https://www.chalmersstudentbostader.se/mina-sidor/",
        },
    )

    if "Fast2User_ssoId" not in sess.cookies.keys():
        raise AuthenticationError("wp-login.php failed")

def login_aptus(sess: requests.sessions.Session):
    data = sess.get(
        "https://www.chalmersstudentbostader.se/widgets/",
        params={
            "callback": "mjau",
            "widgets[]": "aptuslogin@APTUSPORT",
        },
    )
    if data.status_code != 200:
        raise AuthenticationError("aptus login url @ /widgets/")

    json_data = json.loads(data.text[5:-2])
    try:
        aptus_url = json_data["data"]["aptuslogin@APTUSPORT"]["objekt"][0]["aptusUrl"]
    except ValueError as e:
        raise AuthenticationError("aptus login url @ /widgets/")

    resp = sess.get(aptus_url) # this sets login-cookies
    if resp.status_code != 200:
        raise AuthenticationError("aptus login url")

def unlock_door(sess: requests.sessions.Session, door: Door):
    resp = sess.get(
        f"https://apt-www.chalmersstudentbostader.se/AptusPortal/Lock/UnlockEntryDoor/{door.id}",
    )
    if resp.status_code != 200:
        raise AuthenticationError("/UnlockEntryDoor/")

if __name__ == "__main__":
    def main():
        secrets = Secrets.from_toml_file("./secrets.toml")
        with DoorControl(secrets) as dc:
            dc.unlock_door(secrets.doors[0])

    main()
