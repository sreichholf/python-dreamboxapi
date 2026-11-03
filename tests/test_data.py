import unittest
import xml.etree.cElementTree as ET

from dreamboxapi.data import (
    EpgEvent,
    NetworkInterface,
    RemoteControlResult,
    SimpleResult,
)


EVENT_XML = """
<e2event>
    <e2eventid>1234</e2eventid>
    <e2eventstart>1700000000</e2eventstart>
    <e2eventduration>5400</e2eventduration>
    <e2eventremaining>1800</e2eventremaining>
    <e2eventcurrenttime>1700001800.0</e2eventcurrenttime>
    <e2eventprovidername>Provider</e2eventprovidername>
    <e2eventname>News</e2eventname>
    <e2eventtitle>Evening News</e2eventtitle>
    <e2eventdescription>Description</e2eventdescription>
    <e2eventdescriptionextended>Extended description</e2eventdescriptionextended>
</e2event>
"""

INTERFACE_XML = """
<e2interface>
    <e2name>eth0</e2name>
    <e2mac>00:09:34:AA:BB:CC</e2mac>
    <e2dhcp>dhcp</e2dhcp>
    <e2ip>192.168.2.10</e2ip>
    <e2gateway>192.168.2.1</e2gateway>
    <e2netmask>255.255.255.0</e2netmask>
    <e2method6>manual</e2method6>
    <e2ip6>fd00::10</e2ip6>
    <e2gateway6>fd00::1</e2gateway6>
    <e2netmask6>64</e2netmask6>
</e2interface>
"""


class EpgEventTests(unittest.TestCase):
    def test_duration_and_remaining_are_seconds(self):
        event = EpgEvent(ET.fromstring(EVENT_XML))

        self.assertEqual(event.duration, 5400)
        self.assertEqual(event.remaining, 1800)
        self.assertEqual(event.duration_minutes, 90)
        self.assertEqual(event.remaining_minutes, 30)


class NetworkInterfaceTests(unittest.TestCase):
    def test_ipv6_fields_come_from_ip6_and_gateway6(self):
        interface = NetworkInterface(ET.fromstring(INTERFACE_XML))

        self.assertEqual(interface.ip6, "fd00::10")
        self.assertEqual(interface.gateway6, "fd00::1")
        self.assertEqual(interface.netmask6, "64")

    def test_missing_fields_become_empty_strings(self):
        interface = NetworkInterface(
            ET.fromstring("<e2interface><e2name>eth0</e2name></e2interface>")
        )

        self.assertEqual(interface.ip6, "")
        self.assertEqual(interface.gateway6, "")
        self.assertFalse(interface.dhcp)


class SimpleResultTests(unittest.TestCase):
    def test_parses_e2state_tags(self):
        element = ET.fromstring(
            "<e2simplexmlresult>"
            "<e2state>True</e2state>"
            "<e2statetext>Active service is now 'News'</e2statetext>"
            "</e2simplexmlresult>"
        )

        result = SimpleResult(element)

        self.assertTrue(result.state)
        self.assertEqual(result.text, "Active service is now 'News'")


class RemoteControlResultTests(unittest.TestCase):
    def test_parses_e2result_tags(self):
        element = ET.fromstring(
            "<e2remotecontrol>"
            "<e2result>True</e2result>"
            "<e2resulttext>RC command '207' has been issued</e2resulttext>"
            "</e2remotecontrol>"
        )

        result = RemoteControlResult(element)

        self.assertTrue(result.state)
        self.assertEqual(result.text, "RC command '207' has been issued")

    def test_missing_result_text_is_empty(self):
        element = ET.fromstring(
            "<e2remotecontrol><e2result>False</e2result></e2remotecontrol>"
        )

        result = RemoteControlResult(element)

        self.assertFalse(result.state)
        self.assertEqual(result.text, "")

    def test_result_state_allows_surrounding_whitespace(self):
        element = ET.fromstring(
            "<e2remotecontrol><e2result>\n True\n</e2result></e2remotecontrol>"
        )

        result = RemoteControlResult(element)

        self.assertTrue(result.state)


if __name__ == "__main__":
    unittest.main()
