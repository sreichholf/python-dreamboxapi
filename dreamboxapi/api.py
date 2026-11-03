import logging

import requests
from urllib.parse import urlencode

import xml.etree.cElementTree as ET

from dreamboxapi.data import (
    Service,
    ServiceList,
    DeviceInfo,
    RemoteControlResult,
    SimpleResult,
    Volume,
)
from dreamboxapi.exceptions import (
    DreamboxAuthenticationError,
    DreamboxConnectionError,
    DreamboxProtocolError,
)

_LOGGER = logging.getLogger(__name__)


def enable_logging():
    """ Setup the logging for home assistant. """
    logging.basicConfig(level=logging.INFO)


class AuthenticationFailed(DreamboxAuthenticationError):
    """The webinterface rejected the configured credentials."""

    def __init__(self, response=None):
        super().__init__("Authentication with the dreambox failed")
        self.response = response


class DreamboxApi(object):
    URL_ALLSERVICES = "/web/getallservices"
    URL_CURRENT = "/web/getcurrent"
    URL_DEVICEINFO = "/web/deviceinfo"
    URL_FILE = "/file"
    URL_SESSION = "/web/session"
    URL_SERVICES = "/web/getservices"
    URL_POWERSTATE = "/web/powerstate"
    URL_REMOTECONTROL = "/web/remotecontrol"
    URL_VOLUME = "/web/vol"
    URL_ZAP = "/web/zap"

    DEFAULT_TIMEOUT = 10
    BOUQUET_TIMEOUT = 30

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
    KEY_PAUSE = 119
    KEY_STOP = 128
    KEY_PLAY_PAUSE = 164
    KEY_PLAY = 207
    KEY_LEFT = 105
    KEY_RIGHT = 106

    def __init__(
        self,
        host=None,
        port=80,
        user=None,
        password=None,
        https=False,
        bouquet=None,
        piconpath=None,
        timeout=DEFAULT_TIMEOUT,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._pass = password
        self._https = https
        self._defaultBouquet = bouquet
        self._bouquet = None
        self._piconPath = piconpath
        self._timeout = timeout

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
        try:
            self.get_deviceinfo()
        except (DreamboxConnectionError, DreamboxProtocolError) as err:
            _LOGGER.debug("Device info update failed: %s", err)
        self.update_status()
        self.get_bouquets()

    def update_status(self):
        """Refresh the current service and power state."""
        self.get_current()
        self.get_powerstate()

    def close(self):
        self._session.close()

    def _getStandby(self):
        return self._instandby

    def _setStandby(self, standby):
        result = self.set_powerstate(
            DreamboxApi.POWER_STANDBY if standby else DreamboxApi.POWER_WAKEUP
        )
        if result is not None:
            self._instandby = standby
        self.get_powerstate()

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

    def get_picon(self, service=None):
        url = self.picon(service)
        if not url:
            return (None, None)

        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as err:
            _LOGGER.debug("Picon request to %s failed: %s", url, err)
            raise DreamboxConnectionError(str(err)) from err

        if response.status_code == 401:
            raise AuthenticationFailed(response)
        if response.status_code == 404:
            return (None, None)
        if response.status_code != 200:
            raise DreamboxProtocolError(
                "Unexpected HTTP status {} for {}".format(response.status_code, url)
            )

        content_type = response.headers.get("Content-Type") or "image/png"
        return (response.content, content_type)

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
        return self.set_remotekeypress(DreamboxApi.KEY_STOP)

    def play(self):
        return self.set_remotekeypress(DreamboxApi.KEY_PLAY)

    def pause(self):
        return self.set_remotekeypress(DreamboxApi.KEY_PAUSE)

    def togglePlayPause(self):
        return self.set_remotekeypress(DreamboxApi.KEY_PLAY_PAUSE)

    def tooglePlayPause(self):
        return self.togglePlayPause()

    def set_channel_up(self):
        """Zap to the next service using the live-TV right-arrow key."""
        return self.set_remotekeypress(DreamboxApi.KEY_RIGHT)

    def set_channel_down(self):
        """Zap to the previous service using the live-TV left-arrow key."""
        return self.set_remotekeypress(DreamboxApi.KEY_LEFT)

    def _call(self, url, data=None, timeout=None, retry_session=True):
        data = dict(data or {})
        if self._sessionid is not None:
            data["sessionid"] = self._sessionid
        timeout = timeout if timeout is not None else self._timeout

        try:
            response = self._session.post(url, data=data, timeout=timeout)
            _LOGGER.debug("HTTP Response Code: {}".format(response.status_code))
            if response.status_code == 412:  # precondition failed, session invalid
                if not retry_session:
                    raise DreamboxProtocolError(
                        "Session request was rejected with HTTP 412"
                    )
                _LOGGER.debug("Precondition Failed - Acquiring new session")
                self.get_session()
                if self._sessionid:
                    data["sessionid"] = self._sessionid
                response = self._session.post(url, data=data, timeout=timeout)
        except requests.RequestException as err:
            self._available = False
            _LOGGER.debug("Request to %s failed: %s", url, err)
            raise DreamboxConnectionError(str(err)) from err

        if response.status_code == 401:
            self._available = False
            raise AuthenticationFailed(response)
        if response.status_code != 200:
            self._available = False
            _LOGGER.debug(
                "Request failed with '{}' for '{}'".format(
                    response.status_code, url
                )
            )
            raise DreamboxProtocolError(
                "Unexpected HTTP status {} for {}".format(response.status_code, url)
            )

        try:
            root = ET.fromstring(response.text)
        except (ET.ParseError, LookupError, TypeError, ValueError) as err:
            self._available = False
            _LOGGER.debug("Could not parse response from %s: %s", url, err)
            raise DreamboxProtocolError(
                "Invalid XML response from {}".format(url)
            ) from err

        self._available = True
        return root

    def _url(self, path):
        return "{}{}".format(self._baseUrl, path)

    def get_session(self):
        self._sessionid = None
        root = self._call(
            self._url(DreamboxApi.URL_SESSION), retry_session=False
        )
        self._sessionid = (root.text or "").strip() or None
        if self._sessionid:
            _LOGGER.debug(
                "Session acquired, sessionid is '..{}'".format(self._sessionid[-5:])
            )
        else:
            _LOGGER.debug("Session request returned no session id")

    def get_powerstate(self):
        return self.set_powerstate(DreamboxApi.POWER_GET)

    def set_powerstate(self, state):
        _LOGGER.debug("set_powerstate({})".format(state))
        root = self._call(
            self._url(DreamboxApi.URL_POWERSTATE), data={"newstate": state}
        )
        state_text = root.findtext("e2instandby")
        if state_text is not None:
            state_text = state_text.strip().lower()
        if state_text not in ("true", "false"):
            return None
        result = state_text == "true"
        if state == DreamboxApi.POWER_GET:
            self._instandby = result
            _LOGGER.debug(self._instandby)
        return result

    def get_volume(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME))
        self._volume = Volume(root)

    def set_volume(self, target):
        root = self._call(
            self._url(DreamboxApi.URL_VOLUME), {"set": "set{}".format(target)}
        )
        self._volume = Volume(root)

    def set_volumeUp(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "up"})
        self._volume = Volume(root)

    def set_volumeDown(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "down"})
        self._volume = Volume(root)

    def set_volumeToggleMute(self):
        root = self._call(self._url(DreamboxApi.URL_VOLUME), {"set": "mute"})
        self._volume = Volume(root)

    def get_deviceinfo(self):
        root = self._call(self._url(DreamboxApi.URL_DEVICEINFO))
        self._deviceinfo = DeviceInfo(root)

    def get_current(self):
        root = self._call(self._url(DreamboxApi.URL_CURRENT))
        service = root.find("e2service")
        events = root.find("e2eventlist")
        if service is None:
            self._current = None
        else:
            self._current = Service(service, events=events)
        volume = root.find("e2volume")
        if volume is not None:
            self._volume = Volume(volume)

    def get_services(self, ref, cls=Service):
        root = self._call(self._url(DreamboxApi.URL_SERVICES), data={"sRef": ref})
        services = []
        for service in root.iter("e2service"):
            services.append(cls(service))
        return services

    def get_all_services(self, sref):
        root = self._call(
            self._url(DreamboxApi.URL_ALLSERVICES),
            data={"sRef": sref},
            timeout=DreamboxApi.BOUQUET_TIMEOUT,
        )
        bouquets = []
        for element in root.iter("e2bouquet"):
            bouquet = ServiceList(element)
            servicelist = element.find("e2servicelist")
            if servicelist is not None:
                bouquet.services = [
                    Service(service) for service in servicelist.findall("e2service")
                ]
            bouquets.append(bouquet)
        for element in root.findall("e2service"):
            bouquet = ServiceList(element)
            bouquet.services = []
            bouquets.append(bouquet)
        return bouquets

    def get_bouquets(self):
        self._bouquets = self.get_all_services(DreamboxApi.TV_BOUQUETS)
        self._bouquets.extend(self.get_all_services(DreamboxApi.RADIO_BOUQUETS))
        self._bouquet = None
        if not self._bouquets:
            return
        for b in self._bouquets:
            if b.ref == self._defaultBouquet:
                self._bouquet = b
            _LOGGER.debug("Bouquet: {} ({})".format(b.name, len(b.services)))
        if not self._bouquet:
            self._bouquet = self._bouquets[0]

    def set_remotekeypress(self, code):
        root = self._call(
            self._url(DreamboxApi.URL_REMOTECONTROL), data={"command": code}
        )
        return RemoteControlResult(root)

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
        result = SimpleResult(root)
        if not result.state:
            _LOGGER.warning("Play failed with: {}".format(result.text))
        else:
            self.get_current()
        return result
