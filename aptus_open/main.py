from dataclasses import dataclass
from time import sleep
import paho.mqtt.client as mqtt
import json
import argparse
import logging
from aptus_open.lib import Door, DoorControl, Secrets, AuthenticationError

log = logging.getLogger("web")

@dataclass
class MQTTUserdata:
    device_descr: dict
    dc: DoorControl

def make_door_btn_entry(door: Door):
    door_discovery_obj = {
        "p": "button",
        "name": f"Open {door.name}",
        "payload_press": f"open_{door.id}",
        "unique_id": f"apto_open_{door.id}",
    }

    if door.icon != None:
        door_discovery_obj["icon"] = door.icon
    else:
        door_discovery_obj["icon"] = "mdi:lock-open-variant"

    return door_discovery_obj

def make_door_sens_entry(door: Door):
    door_discovery_obj = {
        "p": "binary_sensor",
        "name": f"{door.name} is open",
        "unique_id": f"apto_is_open_{door.id}",
        "off_delay": 5,
        "state_topic": f"home/aptus_open/{door.id}/state"
    }

    door_discovery_obj["icon"] = "mdi:door"

    return door_discovery_obj

def make_mqtt_cmps(secrets: Secrets):
    cmps = {}
    for door in secrets.doors:
        cmps[f"door_{door.id}"] = make_door_btn_entry(door)
        cmps[f"door_isopen_{door.id}"] = make_door_sens_entry(door)

    return cmps

def on_connect(client: mqtt.Client, userdata: MQTTUserdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    client.subscribe("$SYS/#")
    client.subscribe(f"home/aptus_open/command")

    client.publish(f"homeassistant/device/aptus_open/config", bytes(json.dumps(userdata.device_descr), "ascii"), qos=2, retain=True)
    for door in userdata.dc.secrets.doors:
        client.publish(f"home/aptus_open/{door.id}/state", b"OFF", qos=2, retain=True)

def on_message(client: mqtt.Client, userdata: MQTTUserdata, msg):
    if msg.topic != f"home/aptus_open/command":
        return

    print(msg.topic+" "+str(msg.payload))
    if msg.payload.startswith(b"open_"):
        door_id = str(msg.payload[5:], "ascii")
        door = next(door for door in userdata.dc.secrets.doors if door.id == door_id)
        userdata.dc.unlock_door(door)
        client.publish(f"home/aptus_open/{door.id}/state", b"ON", qos=2, retain=False)

def main():
    parser = argparse.ArgumentParser(prog="aptus-open")
    parser.add_argument("-s", "--secrets-file", type=str, required=True, help="path to secrets toml-file")

    env = parser.parse_args()
    secrets = Secrets.from_toml_file(env.secrets_file)

    device_descr = {
        "dev": {
            "ids": f"aptus_open",
            "name": f"Aptus Open",
            "mf": "SA6NYA/TRN",
            "sn": f"no",
            "sw": "1.0",
            "hw": "1.0",
        },
        "o": {
            "name": "Aptus Open",
            "sw": "1.0",
            "url": "https://coral.shoes/"
        },
        "command_topic": f"home/aptus_open/command",
        "cmps": make_mqtt_cmps(secrets),
        "qos": 2
    }

    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    with DoorControl(secrets) as dc:
        mqttc.user_data_set(MQTTUserdata(device_descr, dc))
        mqttc.username_pw_set(secrets.mqtt_username, secrets.mqtt_password)
        mqttc.connect(secrets.mqtt_ip, secrets.mqtt_port, 60)
        mqttc.loop_forever()
