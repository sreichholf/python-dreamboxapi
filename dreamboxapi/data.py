from datetime import datetime


"""
<e2deviceinfo>
    <e2enigmaversion>4.3.2r14-5-gb4ae1-2020-12-07</e2enigmaversion>
    <e2imageversion>Experimental 2020-12-07</e2imageversion>
    <e2webifversion>1.9.0</e2webifversion>
    <e2fpversion>None</e2fpversion>
    <e2devicename>dm900</e2devicename>
    ...
"""


class DeviceInfo(object):
    def __init__(self, element):
        self._enigmaVersion = element.findtext("e2enigmaversion") or ""
        self._imageVersion = element.findtext("e2imageversion") or ""
        self._webifVersion = element.findtext("e2webifversion") or ""
        self._deviceName = element.findtext("e2devicename") or ""
        self._interfaces = []
        network = element.find("e2network")
        if network is not None:
            for interface in network:
                self._interfaces.append(NetworkInterface(interface))

    @property
    def enigmaVersion(self):
        return self._enigmaVersion

    @property
    def imageVersion(self):
        return self._imageVersion

    @property
    def webifVersion(self):
        return self._webifVersion

    @property
    def deviceName(self):
        return self._deviceName

    @property
    def interfaces(self):
        return self._interfaces


class EpgEvent(object):
    def __init__(self, element=None):
        self._id = 0
        self._start = 0
        self._duration = 0
        self._remaining = 0
        self._time = 0
        self._provider = ""
        self._name = ""
        self._title = ""
        self._description = ""
        self._extendedDescription = ""
        if element is not None:
            self._id = int(element.findtext("e2eventid") or "0")
            self._start = int(element.findtext("e2eventstart") or "0")
            self._duration = int(element.findtext("e2eventduration") or "0")
            self._remaining = int(element.findtext("e2eventremaining") or "0")
            self._time = float(element.findtext("e2eventcurrenttime") or "0.0")
            self._provider = element.findtext("e2eventprovidername") or "..."
            self._name = element.findtext("e2eventname") or "..."
            self._title = (
                element.findtext("e2eventtitle")
                or element.findtext("e2servicename")
                or "..."
            )
            self._description = element.findtext("e2eventdescription") or "..."
            self._extendedDescription = (
                element.findtext("e2eventdescriptionextended") or "..."
            )

    @property
    def id(self):
        return self._id

    @property
    def start(self):
        if not self._start:
            return "-"
        return datetime.fromtimestamp(self._start).strftime("%H:%M")

    @property
    def duration(self):
        return self._duration

    @property
    def duration_minutes(self):
        return self._duration / 60

    @property
    def remaining(self):
        return self._remaining

    @property
    def remaining_minutes(self):
        return self._remaining / 60

    @property
    def end(self):
        if not self._start or not self._duration:
            return "-"
        return datetime.fromtimestamp(self._start + self._duration).strftime("%H:%M")

    @property
    def time(self):
        return self._time

    @property
    def provider(self):
        return self._provider

    @property
    def name(self):
        return self._name

    @property
    def title(self):
        return self._title

    @property
    def description(self):
        return self._description

    @property
    def extendedDescription(self):
        return self._extendedDescription


"""
<e2interface>
    <e2name>eth0</e2name>
    <e2mac>00:09:34:XX:XX:XX</e2mac>
    <e2dhcp>dhcp</e2dhcp>
    <e2ip>192.168.2.x</e2ip>
    <e2gateway>192.168.2.1</e2gateway>
    <e2netmask>255.255.255.0</e2netmask>
    <e2method6>off</e2method6>
    <e2ip6>::</e2ip6>
    <e2gateway6>::</e2gateway6>
    <e2netmask6>64</e2netmask6>
</e2interface>
"""


class NetworkInterface(object):
    def __init__(self, element):
        self._name = element.findtext("e2name") or ""
        self._mac = element.findtext("e2mac") or ""
        self._dhcp = element.findtext("e2dhcp") == "dhcp"
        self._ip = element.findtext("e2ip") or ""
        self._gateway = element.findtext("e2gateway") or ""
        self._netmask = element.findtext("e2netmask") or ""
        self._method6 = element.findtext("e2method6") or ""
        self._ip6 = element.findtext("e2ip6") or ""
        self._gateway6 = element.findtext("e2gateway6") or ""
        self._netmask6 = element.findtext("e2netmask6") or ""

    @property
    def name(self):
        return self._name

    @property
    def mac(self):
        return self._mac

    @property
    def dhcp(self):
        return self._dhcp

    @property
    def ip(self):
        return self._ip

    @property
    def gateway(self):
        return self._gateway

    @property
    def netmask(self):
        return self._netmask

    @property
    def method6(self):
        return self._method6

    @property
    def ip6(self):
        return self._ip6

    @property
    def gateway6(self):
        return self._gateway6

    @property
    def netmask6(self):
        return self._netmask6


class Service(object):
    def __init__(self, element, events=None):
        self._name = element.findtext("e2servicename") or ""
        self._ref = element.findtext("e2servicereference") or ""
        self._events = []
        if events is not None:
            for event in events.iter("e2event"):
                self._events.append(EpgEvent(event))
        while len(self._events) < 2:
            self._events.append(EpgEvent(element=None))
        self._picon = self._piconName()

    def _piconName(self):
        x = self._ref.split(":")
        if len(x) < 11:  # skip invalid service references
            return ""
        del x[x[10] and 11 or 10 :]  # remove name and empty path
        x[1] = "0"  # replace flags field
        return "{}.png".format("_".join(x).strip("_"))

    @property
    def picon(self):
        return self._picon

    @property
    def name(self):
        return self._name

    @property
    def ref(self):
        return self._ref

    @property
    def events(self):
        return self._events

    @property
    def now(self):
        if self._events:
            return self._events[0]
        return None

    @property
    def next(self):
        if len(self._events) >= 2:
            return self._events[1]
        return None


class ServiceList(Service):
    def __init__(self, element):
        Service.__init__(self, element)
        self._services = []

    def _getServices(self):
        return self._services

    def _setServices(self, services):
        self._services = services

    services = property(_getServices, _setServices)


class SimpleResult(object):
    def __init__(self, element):
        self._state = (element.findtext("e2state") or "").lower() == "true"
        self._text = element.findtext("e2statetext") or ""

    @property
    def state(self):
        return self._state

    @property
    def text(self):
        return self._text


"""
<e2remotecontrol>
	<e2result>True</e2result>
	<e2resulttext>RC command '207' has been issued</e2resulttext>
</e2remotecontrol>
"""


class RemoteControlResult(object):
    def __init__(self, element):
        self._state = (element.findtext("e2result") or "").strip().lower() == "true"
        self._text = element.findtext("e2resulttext") or ""

    @property
    def state(self):
        return self._state

    @property
    def text(self):
        return self._text


"""
<e2volume>
	<e2result>True</e2result>
	<e2resulttext>Lautstärke beträgt nun 90</e2resulttext>
	<e2current>90</e2current>
	<e2ismuted>True</e2ismuted>
</e2volume>
"""


class Volume(object):
    def __init__(self, element):
        self._volume = int(element.findtext("e2current") or 0)
        self._muted = element.findtext("e2ismuted") == "True"

    @property
    def muted(self):
        return self._muted

    @property
    def volume(self):
        return self._volume
