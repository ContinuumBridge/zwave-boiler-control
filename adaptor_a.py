#!/usr/bin/env python
# adaptor_a.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Written by Peter Claydon
#
ModuleName = "boiler-control"
INTERVAL     = 60      # How often to request sensor values

import sys
import time
import os
import logging
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        logging.basicConfig(filename=CB_LOGFILE,level=CB_LOGGING_LEVEL,format='%(asctime)s %(message)s')
        self.status =           "ok"
        self.state =            "stopped"
        self.connected =        False
        self.switchState =      "unknown"
        self.apps =             {"binary_sensor": [],
                                 "connected": []}
        # super's __init__ must be called:
        #super(Adaptor, self).__init__(argv)
        CbAdaptor.__init__(self, argv)
 
    def setState(self, action):
        # error is only ever set from the running state, so set back to running if error is cleared
        if action == "error":
            self.state == "error"
        elif action == "clear_error":
            self.state = "running"
        logging.debug("%s %s state = %s", ModuleName, self.id, self.state)
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def sendCharacteristic(self, characteristic, data, timeStamp):
        msg = {"id": self.id,
               "content": "characteristic",
               "characteristic": characteristic,
               "data": data,
               "timeStamp": timeStamp}
        for a in self.apps[characteristic]:
            reactor.callFromThread(self.sendMessage, msg, a)

    def onStop(self):
        # Mainly caters for situation where adaptor is told to stop while it is starting
        pass

    def pollSensors(self):
        cmd = {"id": self.id,
               "request": "post",
               "address": self.addr,
               "instance": "0",
               "commandClass": "50",
               "action": "Get",
               "value": ""
              }
        self.sendZwaveMessage(cmd)
        reactor.callLater(INTERVAL, self.pollSensors)

    def checkConnected(self):
        if self.updateTime == self.lastUpdateTime:
            self.connected = False
        else:
            self.connected = True
        self.sendCharacteristic("connected", self.connected, time.time())
        self.lastUpdateTime = self.updateTime
        reactor.callLater(INTERVAL + 10, self.checkConnected)

    def onZwaveMessage(self, message):
        #logging.debug("%s %s onZwaveMessage, message: %s", ModuleName, self.id, str(message))
        if message["content"] == "init":
            self.updateTime = 0
            self.lastUpdateTime = time.time()
            # Switch state
            cmd = {"id": self.id,
                   "request": "get",
                   "address": self.addr,
                   "instance": "0",
                   "commandClass": "37",
                   "value": "level"
                  }
            self.sendZwaveMessage(cmd)
            reactor.callLater(30, self.pollSensors)
            reactor.callLater(INTERVAL, self.checkConnected)
        elif message["content"] == "data":
            try:
                if message["commandClass"] == "50":
                    if message["data"]["name"] == "0":
                        energy = message["data"]["val"]["value"] 
                        logging.debug("%s %s onZwaveMessage, energy (KWh): %s", ModuleName, self.id, str(energy))
                        self.sendCharacteristic("energy", energy, time.time())
                    elif message["data"]["name"] == "6":
                        power_factor = message["data"]["val"]["value"] 
                        logging.debug("%s %s onZwaveMessage, power_factor: %s", ModuleName, self.id, str(power_factor))
                        self.sendCharacteristic("power_factor", power_factor, time.time())
                elif message["commandClass"] == "37":
                    if message["data"]["name"] == "level":
                        if message["data"]["value"]:
                            b = "on"
                        else:
                            b = "off"
                        self.switchState = b
                        logging.debug("%s %s onZwaveMessage, switch state: %s", ModuleName, self.id, b)
                        self.sendCharacteristic("binary_sensor", b, time.time())
                self.updateTime = message["data"]["updateTime"]
            except:
                logging.warning("%s %s onZwaveMessage, unexpected message", ModuleName, str(message))

    def onOff(self, s):
        if s == "on":
            return "255"
        else:
            return "0"

    def switch(self, onOrOff):
        cmd = {"id": self.id,
               "request": "post",
               "address": self.addr,
               "instance": "0",
               "commandClass": "0x25",
               "action": "Set",
               "value": self.onOff(onOrOff)
              }
        self.sendZwaveMessage(cmd)

    def onAppInit(self, message):
        #logging.debug("%s %s %s onAppInit, req = %s", ModuleName, self.id, self.friendly_name, message)
        resp = {"name": self.name,
                "id": self.id,
                "status": "ok",
                "service": [{"characteristic": "connected", "interval": INTERVAL, "type": "switch"},
                            {"characteristic": "binary_sensor", "interval": INTERVAL, "type": "switch"},
                            {"characteristic": "switch", "interval": 0}],
                "content": "service"}
        self.sendMessage(resp, message["id"])
        self.setState("running")

    def onAppRequest(self, message):
        #logging.debug("%s %s %s onAppRequest, message = %s", ModuleName, self.id, self.friendly_name, message)
        # Switch off anything that already exists for this app
        for a in self.apps:
            if message["id"] in self.apps[a]:
                self.apps[a].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if message["id"] not in self.apps[f["characteristic"]]:
                self.apps[f["characteristic"]].append(message["id"])
        logging.debug("%s %s %s apps: %s", ModuleName, self.id, self.friendly_name, str(self.apps))

    def onAppCommand(self, message):
        logging.debug("%s %s %s onAppCommand, req = %s", ModuleName, self.id, self.friendly_name, message)
        if "data" not in message:
            logging.warning("%s %s %s app message without data: %s", ModuleName, self.id, self.friendly_name, message)
        elif message["data"] != "on" and message["data"] != "off":
            logging.warning("%s %s %s app switch state must be on or off: %s", ModuleName, self.id, self.friendly_name, message)
        else:
            if message["data"] != self.switchState:
                self.switch(message["data"])

    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        logging.debug("%s onConfigureMessage, config: %s", ModuleName, config)
        self.setState("starting")

if __name__ == '__main__':
    Adaptor(sys.argv)
