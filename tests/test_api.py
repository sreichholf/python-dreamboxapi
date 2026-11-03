import unittest
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError as RequestsConnectionError

from dreamboxapi.api import AuthenticationFailed, DreamboxApi
from dreamboxapi.data import RemoteControlResult, SimpleResult
from dreamboxapi.exceptions import (
    DreamboxAuthenticationError,
    DreamboxConnectionError,
    DreamboxProtocolError,
)


REMOTE_CONTROL_OK = (
    "<e2remotecontrol>"
    "<e2result>True</e2result>"
    "<e2resulttext>RC command '106' has been issued</e2resulttext>"
    "</e2remotecontrol>"
)

CURRENT_OK = (
    "<e2current>"
    "<e2service>"
    "<e2servicename>Das Erste HD</e2servicename>"
    "<e2servicereference>1:0:19:2B66:3F3:1:C00000:0:0:0:</e2servicereference>"
    "</e2service>"
    "<e2volume>"
    "<e2current>40</e2current>"
    "<e2ismuted>False</e2ismuted>"
    "</e2volume>"
    "</e2current>"
)

FAVOURITES_REF = "1:7:1:0:0:0:0:0:0:0:FAVOURITES"
NEWS_REF = "1:7:1:0:0:0:0:0:0:0:NEWS"

TV_ALL_SERVICES_OK = """
<e2servicelist>
    <e2bouquet>
        <e2servicename>Favourites (TV)</e2servicename>
        <e2servicereference>{favourites}</e2servicereference>
        <e2servicelist>
            <e2service>
                <e2servicename>Das Erste HD</e2servicename>
                <e2servicereference>1:0:19:2B66:3F3:1:C00000:0:0:0:</e2servicereference>
            </e2service>
            <e2service>
                <e2servicename>ZDF HD</e2servicename>
                <e2servicereference>1:0:19:2B66:3F3:2:C00000:0:0:0:</e2servicereference>
            </e2service>
        </e2servicelist>
    </e2bouquet>
    <e2bouquet>
        <e2servicename>News</e2servicename>
        <e2servicereference>{news}</e2servicereference>
        <e2servicelist>
            <e2service>
                <e2servicename>Tagesschau</e2servicename>
                <e2servicereference>1:0:19:2B66:3F3:3:C00000:0:0:0:</e2servicereference>
            </e2service>
        </e2servicelist>
    </e2bouquet>
</e2servicelist>
""".format(
    favourites=FAVOURITES_REF, news=NEWS_REF
)


def _response(text="", status_code=200):
    response = Mock()
    response.status_code = status_code
    response.text = text
    return response


def _image_response(content=b"", content_type=None, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.content = content
    response.headers = {}
    if content_type:
        response.headers["Content-Type"] = content_type
    return response


def _powerstate(instandby):
    return _response(
        "<e2powerstate><e2instandby>{}</e2instandby></e2powerstate>".format(instandby)
    )


class DreamboxApiTestCase(unittest.TestCase):
    def setUp(self):
        post_patcher = patch("dreamboxapi.api.requests.Session.post")
        self.post = post_patcher.start()
        self.addCleanup(post_patcher.stop)
        get_patcher = patch("dreamboxapi.api.requests.Session.get")
        self.get = get_patcher.start()
        self.addCleanup(get_patcher.stop)
        self.post.return_value = _response(REMOTE_CONTROL_OK)
        self.get.return_value = _image_response()
        self.api = DreamboxApi(host="dreambox")

    def posted_url(self, index=-1):
        return self.post.call_args_list[index][0][0]

    def posted_data(self, index=-1):
        return self.post.call_args_list[index][1]["data"]

    def posted_power_states(self):
        return [call[1]["data"]["newstate"] for call in self.post.call_args_list]


class CallTests(DreamboxApiTestCase):
    def test_default_timeout_is_passed_to_post(self):
        self.api.get_deviceinfo()

        self.assertEqual(self.post.call_args[1]["timeout"], 10)

    def test_configured_timeout_is_passed_to_post(self):
        api = DreamboxApi(host="dreambox", timeout=3)

        api.get_deviceinfo()

        self.assertEqual(self.post.call_args[1]["timeout"], 3)

    def test_available_is_set_only_after_successful_parse(self):
        self.assertFalse(self.api.available)

        self.api.get_deviceinfo()

        self.assertTrue(self.api.available)

    def test_401_raises_authentication_failed(self):
        self.post.return_value = _response("", status_code=401)

        with self.assertRaises(AuthenticationFailed):
            self.api.get_deviceinfo()

        self.assertFalse(self.api.available)

    def test_authentication_failed_is_a_dreambox_authentication_error(self):
        self.assertTrue(
            issubclass(AuthenticationFailed, DreamboxAuthenticationError)
        )

    def test_non_200_raises_protocol_error(self):
        self.post.return_value = _response("", status_code=500)

        with self.assertRaises(DreamboxProtocolError):
            self.api.get_deviceinfo()

        self.assertFalse(self.api.available)

    def test_invalid_xml_raises_protocol_error(self):
        self.post.return_value = _response("<e2deviceinfo>")

        with self.assertRaises(DreamboxProtocolError):
            self.api.get_deviceinfo()

        self.assertFalse(self.api.available)

    def test_connection_error_raises_dreambox_connection_error(self):
        self.post.side_effect = RequestsConnectionError("unreachable")

        with self.assertRaises(DreamboxConnectionError):
            self.api.get_deviceinfo()

        self.assertFalse(self.api.available)

    def test_412_retries_with_a_new_session(self):
        self.post.side_effect = [
            _response("", status_code=412),
            _response("<e2session>session-token</e2session>"),
            _response(CURRENT_OK),
        ]

        self.api.get_current()

        self.assertEqual(self.post.call_count, 3)
        self.assertEqual(self.posted_url(1), "http://dreambox:80/web/session")
        self.assertEqual(self.posted_data(2), {"sessionid": "session-token"})
        self.assertEqual(self.api.current.name, "Das Erste HD")
        self.assertTrue(self.api.available)

    def test_412_on_session_request_raises_protocol_error(self):
        self.post.side_effect = [
            _response("", status_code=412),
            _response("", status_code=412),
        ]

        with self.assertRaises(DreamboxProtocolError):
            self.api.get_current()

        self.assertEqual(self.post.call_count, 2)
        self.assertFalse(self.api.available)

    def test_get_session_clears_stale_id_on_failure(self):
        self.api._sessionid = "stale-token"
        self.post.return_value = _response("", status_code=500)

        with self.assertRaises(DreamboxProtocolError):
            self.api.get_session()

        self.assertIsNone(self.api._sessionid)

    def test_call_copies_caller_data(self):
        self.api._sessionid = "session-token"
        data = {"sRef": "bouquet"}
        self.post.return_value = _response("<e2servicelist />")

        self.api._call("http://dreambox:80/web/getservices", data)

        self.assertEqual(data, {"sRef": "bouquet"})
        self.assertEqual(
            self.posted_data(), {"sRef": "bouquet", "sessionid": "session-token"}
        )


class UpdateStatusTests(DreamboxApiTestCase):
    def test_update_status_requests_current_and_power_only(self):
        self.post.side_effect = [
            _response(CURRENT_OK),
            _powerstate(False),
        ]

        self.api.update_status()

        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(
            [call[0][0] for call in self.post.call_args_list],
            [
                "http://dreambox:80/web/getcurrent",
                "http://dreambox:80/web/powerstate",
            ],
        )
        self.assertEqual(self.posted_data(1), {"newstate": -1})
        self.assertEqual(self.api.current.name, "Das Erste HD")
        self.assertFalse(self.api.standby)


class UpdateTests(DreamboxApiTestCase):
    def test_update_refreshes_deviceinfo_status_and_bouquets(self):
        self.post.side_effect = [
            _response("<e2deviceinfo />"),
            _response(CURRENT_OK),
            _powerstate(False),
            _response(TV_ALL_SERVICES_OK),
            _response("<e2servicelist />"),
        ]

        self.api.update()

        self.assertEqual(self.post.call_count, 5)
        self.assertEqual(
            [call[0][0] for call in self.post.call_args_list],
            [
                "http://dreambox:80/web/deviceinfo",
                "http://dreambox:80/web/getcurrent",
                "http://dreambox:80/web/powerstate",
                "http://dreambox:80/web/getallservices",
                "http://dreambox:80/web/getallservices",
            ],
        )
        self.assertIsNotNone(self.api.deviceinfo)
        self.assertEqual(self.api.current.name, "Das Erste HD")
        self.assertEqual(len(self.api.bouquets), 2)


class UpdateFailureTests(DreamboxApiTestCase):
    def test_update_continues_when_deviceinfo_fails(self):
        self.post.side_effect = [
            _response("", status_code=500),
            _response(CURRENT_OK),
            _powerstate(False),
            _response(TV_ALL_SERVICES_OK),
            _response("<e2servicelist />"),
        ]

        self.api.update()

        self.assertEqual(self.post.call_count, 5)
        self.assertIsNone(self.api.deviceinfo)
        self.assertEqual(self.api.current.name, "Das Erste HD")
        self.assertEqual(len(self.api.bouquets), 2)


class VolumeTests(DreamboxApiTestCase):
    def test_muted_is_none_without_volume_state(self):
        self.api._volume = None

        self.assertIsNone(self.api.muted)


class CurrentTests(DreamboxApiTestCase):
    def test_get_current_without_service_clears_current_and_parses_volume(self):
        self.api._current = Mock()
        self.post.return_value = _response(
            "<e2current>"
            "<e2volume>"
            "<e2current>55</e2current>"
            "<e2ismuted>True</e2ismuted>"
            "</e2volume>"
            "</e2current>"
        )

        self.api.get_current()

        self.assertIsNone(self.api.current)
        self.assertEqual(self.api.volume, 55)
        self.assertTrue(self.api.muted)

    def test_get_current_without_volume_keeps_existing_volume(self):
        self.api._volume = None
        self.post.return_value = _response(
            "<e2current>"
            "<e2service>"
            "<e2servicename>Das Erste HD</e2servicename>"
            "<e2servicereference>1:0:19:2B66:3F3:1:C00000:0:0:0:</e2servicereference>"
            "</e2service>"
            "</e2current>"
        )

        self.api.get_current()

        self.assertEqual(self.api.current.name, "Das Erste HD")
        self.assertIsNone(self.api._volume)


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


class BouquetTests(DreamboxApiTestCase):
    def test_get_all_services_parses_nested_bouquets(self):
        self.post.return_value = _response(TV_ALL_SERVICES_OK)

        bouquets = self.api.get_all_services("1:7:1:all")

        self.assertEqual(self.posted_url(), "http://dreambox:80/web/getallservices")
        self.assertEqual(self.posted_data(), {"sRef": "1:7:1:all"})
        self.assertEqual(self.post.call_args[1]["timeout"], 30)
        self.assertEqual(len(bouquets), 2)
        self.assertEqual(bouquets[0].name, "Favourites (TV)")
        self.assertEqual(len(bouquets[0].services), 2)
        self.assertEqual(bouquets[0].services[0].name, "Das Erste HD")
        self.assertEqual(bouquets[1].name, "News")
        self.assertEqual(len(bouquets[1].services), 1)
        self.assertEqual(bouquets[1].services[0].name, "Tagesschau")

    def test_get_bouquets_does_not_request_each_bouquet(self):
        self.post.side_effect = [
            _response(TV_ALL_SERVICES_OK),
            _response("<e2servicelist />"),
        ]

        self.api.get_bouquets()

        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(
            [call[0][0] for call in self.post.call_args_list],
            [
                "http://dreambox:80/web/getallservices",
                "http://dreambox:80/web/getallservices",
            ],
        )
        self.assertEqual(self.posted_data(0), {"sRef": DreamboxApi.TV_BOUQUETS})
        self.assertEqual(self.posted_data(1), {"sRef": DreamboxApi.RADIO_BOUQUETS})
        self.assertEqual(len(self.api.bouquets), 2)
        self.assertEqual(self.api.bouquet.name, "Favourites (TV)")
        self.assertEqual(len(self.api.bouquet.services), 2)

    def test_get_bouquets_selects_the_configured_default(self):
        self.api._defaultBouquet = NEWS_REF
        self.post.side_effect = [
            _response(TV_ALL_SERVICES_OK),
            _response("<e2servicelist />"),
        ]

        self.api.get_bouquets()

        self.assertEqual(self.api.bouquet.ref, NEWS_REF)

    def test_get_all_services_keeps_empty_bouquet(self):
        self.post.return_value = _response(
            "<e2servicelistrecursive>"
            "<e2bouquet>"
            "<e2servicename>Favourites (TV)</e2servicename>"
            "<e2servicereference>{}</e2servicereference>"
            "<e2servicelist>"
            "<e2service>"
            "<e2servicename>Das Erste HD</e2servicename>"
            "<e2servicereference>1:0:19:2B66:3F3:1:C00000:0:0:0:</e2servicereference>"
            "</e2service>"
            "</e2servicelist>"
            "</e2bouquet>"
            "<e2service>"
            "<e2servicename>Empty</e2servicename>"
            "<e2servicereference>{}</e2servicereference>"
            "</e2service>"
            "</e2servicelistrecursive>".format(FAVOURITES_REF, NEWS_REF)
        )

        bouquets = self.api.get_all_services("tv")

        self.assertEqual(len(bouquets), 2)
        self.assertEqual(bouquets[1].name, "Empty")
        self.assertEqual(bouquets[1].services, [])

    def test_get_all_services_without_bouquets_returns_empty_list(self):
        self.post.return_value = _response("<e2servicelist />")

        self.assertEqual(self.api.get_all_services("1:7:1:all"), [])


class PiconTests(DreamboxApiTestCase):
    def setUp(self):
        super().setUp()
        self.api._piconPath = "/picons"
        self.service = Mock()
        self.service.picon = "1_0_19_2B66_3F3_1_C00000_0_0_0.png"

    def test_get_picon_returns_content_and_content_type(self):
        self.get.return_value = _image_response(b"\x89PNG", "image/jpeg")

        content, content_type = self.api.get_picon(self.service)

        self.assertEqual(content, b"\x89PNG")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(
            self.get.call_args[0][0],
            "http://dreambox:80/file"
            "?file=%2Fpicons%2F1_0_19_2B66_3F3_1_C00000_0_0_0.png",
        )
        self.assertEqual(self.get.call_args[1]["timeout"], DreamboxApi.DEFAULT_TIMEOUT)

    def test_get_picon_falls_back_to_png_content_type(self):
        self.get.return_value = _image_response(b"\x89PNG")

        content, content_type = self.api.get_picon(self.service)

        self.assertEqual(content, b"\x89PNG")
        self.assertEqual(content_type, "image/png")

    def test_get_picon_404_returns_none_without_changing_availability(self):
        self.api._available = True
        self.get.return_value = _image_response(status_code=404)

        self.assertEqual(self.api.get_picon(self.service), (None, None))
        self.assertTrue(self.api.available)

    def test_get_picon_401_raises_authentication_failed(self):
        self.get.return_value = _image_response(status_code=401)

        with self.assertRaises(AuthenticationFailed):
            self.api.get_picon(self.service)

    def test_get_picon_other_status_raises_protocol_error(self):
        self.get.return_value = _image_response(status_code=503)

        with self.assertRaises(DreamboxProtocolError):
            self.api.get_picon(self.service)

    def test_get_picon_connection_error_does_not_change_availability(self):
        self.api._available = True
        self.get.side_effect = RequestsConnectionError("unreachable")

        with self.assertRaises(DreamboxConnectionError):
            self.api.get_picon(self.service)

        self.assertTrue(self.api.available)

    def test_get_picon_401_does_not_change_availability(self):
        self.api._available = True
        self.get.return_value = _image_response(status_code=401)

        with self.assertRaises(AuthenticationFailed):
            self.api.get_picon(self.service)

        self.assertTrue(self.api.available)

    def test_get_picon_uses_configured_timeout(self):
        self.api._timeout = 3
        self.get.return_value = _image_response(
            content=b"png", content_type="image/png"
        )

        self.api.get_picon(self.service)

        self.assertEqual(self.get.call_args[1]["timeout"], 3)

    def test_get_picon_without_picon_path_returns_none(self):
        self.api._piconPath = None

        self.assertEqual(self.api.get_picon(self.service), (None, None))
        self.get.assert_not_called()


class CloseTests(DreamboxApiTestCase):
    def test_close_closes_the_session(self):
        with patch.object(self.api._session, "close") as close:
            self.api.close()

        close.assert_called_once_with()


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
