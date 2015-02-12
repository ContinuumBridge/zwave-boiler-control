#!/usr/bin/env python
# adaptor_a.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Written by Peter Claydon
#
ModuleName   = "boiler-control"
INTERVAL     = 15        # How often to check connection

import sys
import time
import os
from cbcommslib import CbAdaptor
from cbconfig import *
from twisted.internet import threads
from twisted.internet import reactor

def state2int(s):
    if s == "on":
        return 1
    else:
        return 0

def int2state(i):
    if i == 1:
        return "on"
    else:
        return "off" 

class Adaptor(CbAdaptor):
    def __init__(self, argv):
        self.status =           "ok"
        self.state =            "stopped"
        self.connected =        False
        self.switchState =      "unknown"
        self.apps =             {"binary_sensor": [],
                                 "switch": [],
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
               "request": "check",
               "address": self.addr
              }
        self.sendZwaveMessage(cmd)
        cmd = {"id": self.id,
               "request": "post",
               "address": self.addr,
               "instance": "0",
               "commandClass": "64",
               "action": "Get",
               "value": ""
              }
        self.sendZwaveMessage(cmd)
        reactor.callLater(INTERVAL, self.pollSensors)

    def checkConnected(self, isFailed):
        #self.cbLog("debug", "checkConnected, isFailed: " + strisFailed))
        if isFailed:
            if self.connected:
                self.sendCharacteristic("connected", False, time.time())
        else:
            if not self.connected:
                self.sendCharacteristic("connected", True, time.time())

    def onZwaveMessage(self, message):
        #self.cbLog("debug", "onZwaveMessage, message: " + str(message))
        if message["content"] == "init":
            self.updateTime = 0
            self.lastUpdateTime = time.time()
            # Switch state
            cmd = {"id": self.id,
                   "request": "get",
                   "address": self.addr,
                   "instance": "0",
                   "commandClass": "64",
                   "value": "mode"
                  }
            self.sendZwaveMessage(cmd)
            cmd = {"id": self.id,
                   "request": "getc",
                   "address": self.addr,
                   "instance": "0",
                   "commandClass": "0"
                  }
            self.sendZwaveMessage(cmd)
            reactor.callLater(30, self.pollSensors)
        elif message["content"] == "data":
            try:
                if message["commandClass"] == "64":
                    if message["value"] == "mode":
                        mode = message["data"]["value"] 
                        self.sendCharacteristic("binary_sensor", int2state(mode), time.time())
                elif message["commandClass"] == "0":
                    if message["data"]["name"] == "isFailed":
                        isFailed = message["data"]["value"] 
                        self.checkConnected(isFailed)
            except:
                self.cbLog("warning", "onZwaveMessage, unexpected message: " + str(message))

    def switch(self, onOrOff):
        cmd = {"id": self.id,
               "request": "post",
               "address": self.addr,
               "instance": "0",
               "commandClass": "64",
               "action": "Set",
               "value": str(state2int(onOrOff))
              }
        self.sendZwaveMessage(cmd)

    def onAppInit(self, message):
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
        # Switch off anything that already exists for this app
        for a in self.apps:
            if message["id"] in self.apps[a]:
                self.apps[a].remove(message["id"])
        # Now update details based on the message
        for f in message["service"]:
            if message["id"] not in self.apps[f["characteristic"]]:
                self.apps[f["characteristic"]].append(message["id"])
        self.cbLog("debug", "apps: " + str(self.apps))

    def onAppCommand(self, message):
        if "data" not in message:
            self.cbLog("warning", "app message without data: " + str(message))
        elif message["data"] != "on" and message["data"] != "off":
            self.cbLog("warning", "appp switch state must be on or off: " + str(message))
        else:
            if message["data"] != self.switchState:
                self.switch(message["data"])

    def onConfigureMessage(self, config):
        """Config is based on what apps are to be connected.
            May be called again if there is a new configuration, which
            could be because a new app has been added.
        """
        self.setState("starting")

if __name__ == '__main__':
    Adaptor(sys.argv)
