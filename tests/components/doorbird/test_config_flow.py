"""Test the DoorBird config flow."""
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import zeroconf
from homeassistant.components.doorbird.const import CONF_EVENTS, DOMAIN
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME

from tests.common import MockConfigEntry

VALID_CONFIG = {
    CONF_HOST: "1.2.3.4",
    CONF_USERNAME: "friend",
    CONF_PASSWORD: "password",
    CONF_NAME: "mydoorbird",
}


def _get_mock_doorbirdapi_return_values(ready=None, info=None):
    doorbirdapi_mock = MagicMock()
    type(doorbirdapi_mock).ready = MagicMock(return_value=ready)
    type(doorbirdapi_mock).info = MagicMock(return_value=info)
    type(doorbirdapi_mock).doorbell_state = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=Mock(status_code=401))
    )
    return doorbirdapi_mock


def _get_mock_doorbirdapi_side_effects(ready=None, info=None):
    doorbirdapi_mock = MagicMock()
    type(doorbirdapi_mock).ready = MagicMock(side_effect=ready)
    type(doorbirdapi_mock).info = MagicMock(side_effect=info)

    return doorbirdapi_mock


async def test_user_form(hass):
    """Test we get the user form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {}

    doorbirdapi = _get_mock_doorbirdapi_return_values(
        ready=[True], info={"WIFI_MAC_ADDR": "macaddr"}
    )
    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ), patch(
        "homeassistant.components.doorbird.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.doorbird.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_CONFIG,
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "1.2.3.4"
    assert result2["data"] == {
        "host": "1.2.3.4",
        "name": "mydoorbird",
        "password": "password",
        "username": "friend",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_zeroconf_wrong_oui(hass):
    """Test we abort when we get the wrong OUI via zeroconf."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            properties={"macaddress": "notdoorbirdoui"},
            host="192.168.1.8",
            name="Doorstation - abc123._axis-video._tcp.local.",
        ),
    )
    assert result["type"] == "abort"
    assert result["reason"] == "not_doorbird_device"


async def test_form_zeroconf_link_local_ignored(hass):
    """Test we abort when we get a link local address via zeroconf."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf.ZeroconfServiceInfo(
            properties={"macaddress": "1CCAE3DOORBIRD"},
            host="169.254.103.61",
            name="Doorstation - abc123._axis-video._tcp.local.",
        ),
    )
    assert result["type"] == "abort"
    assert result["reason"] == "link_local_address"


async def test_form_zeroconf_correct_oui(hass):
    """Test we can setup from zeroconf with the correct OUI source."""
    doorbirdapi = _get_mock_doorbirdapi_return_values(
        ready=[True], info={"WIFI_MAC_ADDR": "macaddr"}
    )

    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                properties={"macaddress": "1CCAE3DOORBIRD"},
                name="Doorstation - abc123._axis-video._tcp.local.",
                host="192.168.1.5",
            ),
        )
        await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ), patch("homeassistant.components.logbook.async_setup", return_value=True), patch(
        "homeassistant.components.doorbird.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.doorbird.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_CONFIG
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "1.2.3.4"
    assert result2["data"] == {
        "host": "1.2.3.4",
        "name": "mydoorbird",
        "password": "password",
        "username": "friend",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "doorbell_state_side_effect",
    [
        requests.exceptions.HTTPError(response=Mock(status_code=404)),
        OSError,
        None,
    ],
)
async def test_form_zeroconf_correct_oui_wrong_device(hass, doorbell_state_side_effect):
    """Test we can setup from zeroconf with the correct OUI source but not a doorstation."""
    doorbirdapi = _get_mock_doorbirdapi_return_values(
        ready=[True], info={"WIFI_MAC_ADDR": "macaddr"}
    )
    type(doorbirdapi).doorbell_state = MagicMock(side_effect=doorbell_state_side_effect)

    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                properties={"macaddress": "1CCAE3DOORBIRD"},
                name="Doorstation - abc123._axis-video._tcp.local.",
                host="192.168.1.5",
            ),
        )
        await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "not_doorbird_device"


async def test_form_user_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    doorbirdapi = _get_mock_doorbirdapi_side_effects(ready=OSError)
    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_CONFIG,
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_user_invalid_auth(hass):
    """Test we handle cannot invalid auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_error = requests.exceptions.HTTPError(response=Mock(status_code=401))
    doorbirdapi = _get_mock_doorbirdapi_side_effects(ready=mock_error)
    with patch(
        "homeassistant.components.doorbird.config_flow.DoorBird",
        return_value=doorbirdapi,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_CONFIG,
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_options_flow(hass):
    """Test config flow options."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcde12345",
        data=VALID_CONFIG,
        options={CONF_EVENTS: ["event1", "event2", "event3"]},
    )
    config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.doorbird.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_EVENTS: "eventa,   eventc,    eventq"}
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert config_entry.options == {CONF_EVENTS: ["eventa", "eventc", "eventq"]}
