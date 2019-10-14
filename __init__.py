"""Kismet integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.device_tracker import (
    CONF_SCAN_INTERVAL,
    DOMAIN as DEVICE_TRACKER,
)
from homeassistant.components.device_tracker.const import (
    SCAN_INTERVAL as DEFAULT_SCAN_INTERVAL,
)
from homeassistant.const import (
    CONF_EXCLUDE,
    CONF_INCLUDE,
    CONF_PASSWORD,
    CONF_PREFIX,
    CONF_USERNAME,
)
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'kismet'
DEFAULT_PREFIX = DOMAIN


CONF_KISMET_SERVER = 'host'
CONF_KISMET_PORT = 'port'
CONF_KISMET_USER = 'user'
CONF_KISMET_PASS = 'pass'
CONF_SSIDS = 'ssids'
CONF_CLIENTS = 'clients'

KISMET_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(CONF_KISMET_SERVER, default='127.0.0.1'): cv.string,
            vol.Required(CONF_KISMET_PORT, default=2501): cv.positive_int,
            vol.Required(CONF_KISMET_USER, default='kismet'): cv.string,
            vol.Required(CONF_KISMET_PASS, default='changeme'): cv.string,
            vol.Optional(CONF_SSIDS, default=[]): cv.ensure_list,
            vol.Optional(CONF_CLIENTS, default=[]): cv.ensure_list
        }
    )
)


#CONFIG_SCHEMA = vol.Schema({DOMAIN: KISMET_SCHEMA}, extra=vol.ALLOW_EXTRA)
CONFIG_SCHEMA =  vol.Schema(
    {
        vol.Required(CONF_KISMET_SERVER, default='127.0.0.1'): cv.string,
        vol.Required(CONF_KISMET_PORT, default=2501): cv.positive_int,
        vol.Required(CONF_KISMET_USER, default='kismet'): cv.string,
        vol.Required(CONF_KISMET_PASS, default='changeme'): cv.string,
        vol.Optional(CONF_SSIDS, default=[]): cv.ensure_list,
        vol.Optional(CONF_CLIENTS, default=[]): cv.ensure_list
    }
)

def setup(hass, config):
    """Set up integration."""
    _LOGGER.debug("Running setup() for kismet platform")
    conf = config.get(DOMAIN, KISMET_SCHEMA({}))
    _LOGGER.debug("Got configuration: {}".format(str(conf)))
    hass.data[DOMAIN] = {"config": conf, "apis": {}}
    discovery.load_platform(hass, DEVICE_TRACKER, DOMAIN, None, config)

    return True
