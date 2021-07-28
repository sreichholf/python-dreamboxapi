import logging

from enum import Enum
import requests
from requests.exceptions import ConnectionError, HTTPError
from urllib.parse import urlencode

import xml.etree.cElementTree as ET

from dreamboxapi.data import Service, ServiceList, DeviceInfo, SimpleResult, Volume

_LOGGER = logging.getLogger(__name__)


def enable_logging():
    """ Setup the logging for home assistant. """
    logging.basicConfig(level=logging.INFO)


class AuthenticationFailed(HTTPError):
    pass


class DreamboxApi(object):
    URL_CURRENT = "/web/getcurrent"
    URL_DEVICEINFO = "/web/deviceinfo"
    URL_FILE = "/file"
    URL_SESSION = "/web/session"
    URL_SERVICES = "/web/getservices"
    URL_POWERSTATE = "/web/powerstate"
    URL_REMOTECONTROL = "/web/remotecontrol"
    URL_VOLUME = "/web/vol"
    URL_ZAP = "/web/zap"

    POWER_GET = -1
    POWER_TOGGLE_STANDBY = 0
    POWER_WAKEUP = 4
    POWER_STANDBY = 5

    TV_BOUQUETS = '1:7:1:0:0:0:0:0:0:0:(type == 1) || (type == 17) || (type == 195) || (type == 25) FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
    RADIO_BOUQUETS = (
        '1:7:2:0:0:0:0:0:0:0:(type == 2)FROM BOUQUET "bouquets.radio" ORDER BY bouquet'
    )

    KEY_VOLUME_DOWN = 114
    KEY_VOLUME_UP = 115
    KEY_STOP = 128
    KEY_PLAY_PAUSE = 207

    def __init__(
        self,
        host=None,
        port=80,
        user=None,
        password=None,
        https=False,
        bouquet=None,
        piconpath=None,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._pass = password
        self._https = https
        self._defaultBouquet = bouquet
        self._bouquet = None
        self._piconPath = piconpath

        if not host:
            _LOGGER.error("DreamboxApi:  Missing Dreambox WebInterface host!")
            raise ValueError("Host not set!")

        self._session = requests.Session()
        self._session.auth = (self._user, self._pass)
        protocol = "https" if self._https else "http"
        self._baseUrl = "{}://{}:{}".format(protocol, self._host, self._port)

        self._instandby = True
        self._available = False

        self._sessionid = None

        self._current = None
        self._volume = None
        self._status = {}
        self._deviceinfo = None
        self._bouquets = []

    def update(self):
        _LOGGER.debug(f"Updating data for {self._baseUrl}")
        self.get_deviceinfo()
        self.get_current()
        self.get_powerstate()
        self.get_bouquets()

    def _getStandby(self):
        return self._instandby

    def _setStandby(self, standby):
        self.set_powerstate(
            DreamboxApi.POWER_STANDBY if standby else DreamboxApi.POWER_WAKEUP
        )

    standby = property(_getStandby, _setStandby)

    @property
    def available(self):
        return self._available

    @property
    def current(self):
        return self._current

    @property
    def bouquets(self):
        return self._bouquets

    @property
    def bouquet(self):
        return self._bouquet

    @property
    def deviceinfo(self):
        return self._deviceinfo

    @property
    def mac(self):
        if self.deviceinfo:
            for nic in self.deviceinfo.interfaces:
                if nic.mac.startswith("00:09:34"):
                    return nic.mac
            if len(self.deviceinfo.interfaces):
                return self.deviceinfo.interfaces[0].mac
        return ""

    def picon(self, service=None):
        if not self._piconPath:
            return None
        if service is None:
            service = self._current
        if service is None:
            return None
        path = "{}/{}".format(self._piconPath, service.picon)
        args = urlencode({"file": path})
        return "{}?{}".format(self._url(DreamboxApi.URL_FILE), args)

    def _getMuted(self):
        return self._volume.muted

    def _setMuted(self, muted):
        self.get_volume()
        if self._volume.muted != muted:
            self.set_volumeToggleMute()

    muted = property(_getMuted, _setMuted)

    def _getVolume(self):
        if not self._volume:
            return 0
        return self._volume.volume

    def _setVolume(self, target):
        self.set_volume(target)

    volume = property(_getVolume, _setVolume)

    def volumeUp(self):
        self.set_volumeUp()

    def volumeDown(self):
        self.set_volumeDown()

    def playService(self, service, bouquet=None):
        if not bouquet:
            bouquet = self._bouquet
        self.set_service(service, bouquet)

    def stop(self):
        self.set_remotekeypress(DreamboxApi.KEY_STOP)

    def tooglePlayPause(self):
        self.set_remotekeypress(DreamboxApi.KEY_PLAY_PAUSE)

    def _call(self, url, data={}):
        try:
            if self._sessionid != None:
                data["sessionid"] = self._sessionid
            response = self._session.post(url, data=data)
            _LOGGER.debug("HTTP Response Code: {}".format(response.status_code))
            if response.status_code == 412:  # precondition failed, session invalid
                _LOGGER.debug("Precondition Failed - Aquiring new session")
                self.get_session()
                if self._sessionid:
                    data["sessionid"] = self._sessionid
                    response = self._session.post(url, data=data)
            self._available = True
            if response.status_code == 401:
                raise AuthenticationFailed(response)
            if response.status_code == 200:
                return ET.fromstring(response.text)
            else:
                _LOGGER.error(
                    "Request failed with '{}' for '{}'".format(
                        response.status_code, url
                    )
                )
        except ConnectionError as e:
            self._available = False
            _LOGGER.warning(f"Connection FAILED ({self._baseUrl}): {e}")

        return None

    def _url(self, path):
        return "{}{}".format(self._baseUrl, path)

    def get_session(self):
        root = self._call(self._url(DreamboxApi.URL_SESSION))
        if root is None:
            _LOGGER.warning("Session request failed!")
            return
        self._sessionid = root.text
        _LOGGER.debug(
            "Session aquired, sessionid is '..{}'".format(self._sessionid[-5:])
        )

    def get_powerstate(self):
        return self.set_powerstate(DreamboxApi.POWER_GET)

    def set_powerstate(self, state):
        _LOGGER.debug("set_powerstate({})".format(state))
        root = self._call(
            self._url(DreamboxApi.URL_POWERSTATE), data={"newstate": state}
        )
        if root is None:
            return
        self._instandby = root.find("e2instandby").text.lower() == "true"
        _LOGGER.debug(self._instandby)

    def get_volume(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME))
        if root is None:
            return
        self._volume = Volume(root)

    def set_volume(self, target):
        root = self._call(
            self._url(DreamboxApi.URL_VOLUME), {"set": "set{}".format(target)}
        )
        if root is None:
            return
        self._volume = Volume(root)

    def set_volumeUp(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "up"})
        if root is None:
            return
        self._volume = Volume(root)

    def set_volumeDown(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "down"})
        if root is None:
            return
        self._volume = Volume(root)

    def set_volumeToggleMute(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "mute"})
        if root is None:
            return
        self._volume = Volume(root)

    def get_deviceinfo(self):
        root = self._call(self._url(DreamboxApi.URL_DEVICEINFO))
        if root is None:
            return
        self._deviceinfo = DeviceInfo(root)

    def get_current(self):
        root = self._call(self._url(DreamboxApi.URL_CURRENT))
        if root is None:
            return
        service = root.find("e2service")
        events = root.find("e2eventlist")
        self._current = Service(service, events=events)
        self._volume = Volume(root.find("e2volume"))

    def get_services(self, ref, cls=Service):
        root = self._call(self._url(DreamboxApi.URL_SERVICES), data={"sRef": ref})
        services = []
        if root is None:
            return services
        for service in root.iter("e2service"):
            services.append(cls(service))
        return services

    def get_bouquets(self):
        self._bouquets = self.get_services(DreamboxApi.TV_BOUQUETS, cls=ServiceList)
        self._bouquets.extend(
            self.get_services(DreamboxApi.RADIO_BOUQUETS, cls=ServiceList)
        )
        if not self._bouquets:
            return
        for b in self._bouquets:
            if b.ref == self._defaultBouquet:
                self._bouquet = b
            b.services = self.get_services(b.ref)
            _LOGGER.debug("Bouquet: {} ({})".format(b.name, len(b.services)))
        if not self._bouquet:
            self._bouquet = self._bouquets[0]

    def set_remotekeypress(self, code):
        root = self._call(self._url(DreamboxApi.URL_ZAP), data={"command": code})
        if root is None:
            return False
        return SimpleResult(root)

    def set_service(self, service, bouquet):
        if not service in bouquet.services:
            _LOGGER.error("'{}' is not in '{}'".format(service.name, bouquet.name))
            return
        url = self._url(DreamboxApi.URL_ZAP)
        data = {
            "sRef": service.ref,
            "root": bouquet.ref,
        }
        root = self._call(url, data=data)
        if root is None:
            return False
        result = SimpleResult(root)
        if not result.state:
            _LOGGER.warning("Play failed with: {}".format(result.text))
        else:
            self.get_current()
        return result
