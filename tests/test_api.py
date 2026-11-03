import unittest
from unittest.mock import Mock, patch

from dreamboxapi.api import DreamboxApi
from dreamboxapi.data import RemoteControlResult, SimpleResult


REMOTE_CONTROL_OK = (
    "<e2remotecontrol>"
    "<e2result>True</e2result>"
    "<e2resulttext>RC command '106' has been issued</e2resulttext>"
    "</e2remotecontrol>"
)


def _response(text):
    response = Mock()
    response.status_code = 200
    response.text = text
    return response


def _powerstate(instandby):
    return _response(
        "<e2powerstate><e2instandby>{}</e2instandby></e2powerstate>".format(instandby)
    )


class DreamboxApiTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch("dreamboxapi.api.requests.Session.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)
        self.post.return_value = _response(REMOTE_CONTROL_OK)
        self.api = DreamboxApi(host="dreambox")

    def posted_url(self, index=-1):
        return self.post.call_args_list[index][0][0]

    def posted_data(self, index=-1):
        return self.post.call_args_list[index][1]["data"]

    def posted_power_states(self):
        return [call[1]["data"]["newstate"] for call in self.post.call_args_list]


class RemoteControlTests(DreamboxApiTestCase):
    def test_set_remotekeypress_posts_command_to_remotecontrol(self):
        result = self.api.set_remotekeypress(106)

        self.assertEqual(self.posted_url(), "http://dreambox:80/web/remotecontrol")
        self.assertEqual(self.posted_data(), {"command": 106})
        self.assertIsInstance(result, RemoteControlResult)
        self.assertTrue(result.state)
        self.assertEqual(result.text, "RC command '106' has been issued")

    def test_remote_key_codes(self):
        cases = (
            ("play", 207),
            ("pause", 119),
            ("togglePlayPause", 164),
            ("tooglePlayPause", 164),
            ("stop", 128),
            ("set_channel_up", 106),
            ("set_channel_down", 105),
        )
        for method, code in cases:
            with self.subTest(method=method):
                self.post.reset_mock()
                self.post.return_value = _response(REMOTE_CONTROL_OK)
                getattr(self.api, method)()

                self.assertEqual(
                    self.posted_url(), "http://dreambox:80/web/remotecontrol"
                )
                self.assertEqual(self.posted_data(), {"command": code})

    def test_channel_keys_use_live_tv_zap_arrows(self):
        self.api.set_channel_up()

        self.assertEqual(self.posted_data(), {"command": 106})

        self.post.reset_mock()
        self.api.set_channel_down()

        self.assertEqual(self.posted_data(), {"command": 105})

    def test_remotecontrol_failure_is_reported(self):
        self.post.return_value = _response(
            "<e2remotecontrol>"
            "<e2result>False</e2result>"
            "<e2resulttext>Missing or wrong argument</e2resulttext>"
            "</e2remotecontrol>"
        )

        result = self.api.set_remotekeypress(999)

        self.assertFalse(result.state)
        self.assertEqual(result.text, "Missing or wrong argument")


class ServiceTests(DreamboxApiTestCase):
    def test_set_service_uses_zap_and_parses_state(self):
        service = Mock()
        service.name = "News"
        service.ref = "1:0:19:..."
        bouquet = Mock()
        bouquet.name = "Favorites"
        bouquet.ref = "1:7:1:..."
        bouquet.services = [service]
        self.post.return_value = _response(
            "<e2simplexmlresult>"
            "<e2state>False</e2state>"
            "<e2statetext>Cannot zap while device is in Standby</e2statetext>"
            "</e2simplexmlresult>"
        )

        result = self.api.set_service(service, bouquet)

        self.assertEqual(self.posted_url(0), "http://dreambox:80/web/zap")
        self.assertEqual(
            self.posted_data(0),
            {"sRef": service.ref, "root": bouquet.ref},
        )
        self.assertIsInstance(result, SimpleResult)
        self.assertFalse(result.state)


class StandbyTests(DreamboxApiTestCase):
    def test_set_standby_true_sends_standby_and_refreshes(self):
        self.post.side_effect = [
            _powerstate(True),
            _powerstate(True),
        ]

        self.api.standby = True

        self.assertEqual(self.posted_power_states(), [5, -1])
        self.assertTrue(self.api.standby)

    def test_set_standby_true_when_already_in_standby_does_not_wake(self):
        self.post.side_effect = [
            # The webinterface returns "false" for command 5 when it was
            # already in standby, but it does not wake the box.
            _powerstate(False),
            _powerstate(True),
        ]

        self.api.standby = True

        self.assertEqual(self.posted_power_states(), [5, -1])
        self.assertTrue(self.api.standby)

    def test_set_standby_false_sends_wakeup_and_refreshes(self):
        self.post.side_effect = [
            _powerstate(False),
            _powerstate(False),
        ]

        self.api.standby = False

        self.assertEqual(self.posted_power_states(), [4, -1])
        self.assertFalse(self.api.standby)

    def test_set_standby_false_when_awake_does_not_sleep(self):
        self.post.side_effect = [
            # The webinterface returns "true" for command 4 when it was
            # already awake, but it does not enter standby.
            _powerstate(True),
            _powerstate(False),
        ]

        self.api.standby = False

        self.assertEqual(self.posted_power_states(), [4, -1])
        self.assertFalse(self.api.standby)

    def test_set_standby_keeps_requested_state_when_refresh_fails(self):
        self.post.side_effect = [
            _powerstate(True),
            _response("<e2powerstate />"),
        ]

        self.api.standby = True

        self.assertEqual(self.posted_power_states(), [5, -1])
        self.assertTrue(self.api.standby)

    def test_set_standby_ignores_false_command_response_if_refresh_fails(self):
        self.post.side_effect = [
            # Command 5 reports "false" when the box was already in standby.
            _powerstate(False),
            _response("<e2powerstate />"),
        ]

        self.api.standby = True

        self.assertEqual(self.posted_power_states(), [5, -1])
        self.assertTrue(self.api.standby)

    def test_set_wakeup_ignores_true_command_response_if_refresh_fails(self):
        self.post.side_effect = [
            # Command 4 reports "true" when the box was already awake.
            _powerstate(True),
            _response("<e2powerstate />"),
        ]

        self.api.standby = False

        self.assertEqual(self.posted_power_states(), [4, -1])
        self.assertFalse(self.api.standby)

    def test_set_standby_ignores_empty_powerstate_text(self):
        self.post.side_effect = [
            _response("<e2powerstate><e2instandby></e2instandby></e2powerstate>"),
            _powerstate(True),
        ]

        self.api.standby = True

        self.assertEqual(self.posted_power_states(), [5, -1])
        self.assertTrue(self.api.standby)

    def test_set_powerstate_empty_or_invalid_text_returns_none(self):
        for value in ("", " ", "error"):
            with self.subTest(value=value):
                self.post.return_value = _response(
                    "<e2powerstate><e2instandby>{}</e2instandby></e2powerstate>".format(
                        value
                    )
                )

                self.assertIsNone(self.api.set_powerstate(5))

    def test_set_powerstate_command_does_not_change_cached_state(self):
        self.api._instandby = False
        self.post.return_value = _powerstate(True)

        result = self.api.set_powerstate(4)

        self.assertTrue(result)
        self.assertFalse(self.api.standby)


if __name__ == "__main__":
    unittest.main()
