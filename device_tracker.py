"""Support kismet device tracking."""
from datetime import timedelta
import logging
import requests
import json
import voluptuous as vol

from homeassistant.components.device_tracker import ( CONF_SCAN_INTERVAL, PLATFORM_SCHEMA, DeviceScanner)
from homeassistant.components.device_tracker.const import (
    ENTITY_ID_FORMAT as DT_ENTITY_ID_FORMAT,
)
from homeassistant.components.zone import async_active_zone
from homeassistant.const import (
    ATTR_BATTERY_CHARGING,
    ATTR_ENTITY_ID,
    CONF_PREFIX,
    LENGTH_FEET,
    LENGTH_KILOMETERS,
    LENGTH_METERS,
    LENGTH_MILES,
    STATE_UNKNOWN
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_time_interval
from homeassistant.util.async_ import run_callback_threadsafe
from homeassistant.util.distance import convert
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

EVENT_DELAY = timedelta(seconds=30)


def setup_scanner(hass, config, see, discovery_info=None):
    """Set up device scanner."""
    #_LOGGER.debug("hass.data: {}".format(hass.data))
    config = hass.data[DOMAIN]["config"]
    apis = hass.data[DOMAIN]["apis"]
    _LOGGER.debug("setup_scanner - creating a KismetScanner")
    KismetScanner(hass, config, see, apis)
    return True


def _utc_from_ts(val):
    try:
        return dt_util.utc_from_timestamp(float(val))
    except (TypeError, ValueError):
        return None

class KismetScanner:
    """Kismet device scanner."""

    def __init__(self, hass, config, see, apis):
        """Initialize KismetScanner."""
        self._hass = hass
        self._see = see

        self._apis = apis
        self._errs = {}
        self._dev_data = {}

        self.server = config[CONF_KISMET_SERVER]
        self.port = config[CONF_KISMET_PORT]
        self.user = config[CONF_KISMET_USER]
        self.password = config[CONF_KISMET_PASS]
        self.scan_interval = config[CONF_SCAN_INTERVAL]
        self.ssids = config[CONF_SSIDS]
        self.clients = config[CONF_CLIENTS]

        self._started = dt_util.utcnow()

        _LOGGER.debug(
            "Params:" + "server: " + self.server + ", port: " + str(self.port) + ", scan_interval (type " + str(
                type(self.scan_interval)) + "): " + str(self.scan_interval))

        # check that either clients or ssids has at least an entry
        if len(self.ssids) or len(self.clients):
            _LOGGER.info(
                "Scanner initialized for " + str(len(self.ssids)) + " SSIDs and " + str(len(self.clients)) + " clients")
        else:
            _LOGGER.error("Kismet device_tracker requires at least a SSID or a client in the configuration")


        self._update_kismet()
        track_time_interval(
            self._hass, self._update_kismet, config[CONF_SCAN_INTERVAL]
        )

    def _prev_seen(self, dev_id, last_seen):
        prev_seen, reported = self._dev_data.get(dev_id, (None, False))

        self._dev_data[dev_id] = last_seen or prev_seen, reported

        return prev_seen

    def _update_device(self, member, dev_id):
        loc = member.get("location")
        try:
            last_seen = _utc_from_ts(loc.get("ts"))
        except AttributeError:
            last_seen = None
        prev_seen = self._prev_seen(dev_id, last_seen)

        if not loc:
            err_msg = "Location information missing"
            _LOGGER.error(dev_id+": "+err_msg)
            return

        # Only update when we truly have an update.
        if not last_seen or prev_seen and last_seen <= prev_seen:
            return

        lat = loc.get("latitude")
        lon = loc.get("longitude")
        gps_accuracy = loc.get("fix")
        try:
            lat = float(lat)
            lon = float(lon)

        except (TypeError, ValueError):
            _LOGGER.error(dev_id+": "+ f"GPS data invalid: {lat}, {lon}, {gps_accuracy}")
            return

        msg = f"Updating {dev_id}"
        if prev_seen:
            msg += "; Time since last update: {}".format(last_seen - prev_seen)
        _LOGGER.debug(msg)

        # If user wants driving or moving to be shown as state, and current
        # location is not in a HA zone, then set location name accordingly.
        loc_name = None
        active_zone = run_callback_threadsafe(
            self._hass.loop, async_active_zone, self._hass, lat, lon, gps_accuracy
        ).result()
        _LOGGER.debug("active_zone is {}".format(str(active_zone)))
        if not active_zone:
            loc_name = None
        # Get raw attribute data, converting empty strings to None.
        attrs = {

        }
        _LOGGER.debug("Calling see() for {} with parameters gps({},{}), location_name={}, gps_accuracy {}, "
                      "battery=100, mac={}, host_name={}".format(
          dev_id, lat, lon, loc_name, gps_accuracy, dev_id, member['name']
        ))

        self._see(
            dev_id=dev_id,
            gps=(lat, lon),
            location_name=loc_name,
            gps_accuracy=gps_accuracy,
            battery=100,
            mac=dev_id,
            host_name=member['name'],
            attributes=attrs,
            picture=None
        )

    def _update_kismet(self, now=None):

        _LOGGER.debug("Preparing kismet query...")
        last_results = []
        # prepare the query
        ssid_gps_prefix = 'dot11.device/dot11.device.last_beaconed_ssid_record/dot11.advertisedssid.location/kismet.common.location.avg_loc'
        client_gps_prefix = 'dot11.device/dot11.device.last_probed_ssid_record/dot11.probedssid.location/kismet.common.location.avg_loc'
        parameters = {}
        parameters['regex'] = []
        
        if len(self.ssids):
            parameters["fields"].append(ssid_gps_prefix)
        
        if len(self.clients):
            parameters["fields"].append(client_gps_prefix)

        for ssid in self.ssids:
            _LOGGER.debug("Adding SSID " + ssid + "...")
            parameters['regex'].append(['kismet.device.base.name', str(ssid)])

        for client in self.clients:
            _LOGGER.debug("Adding client " + client + "...")
            parameters['regex'].append(['kismet.device.base.macaddr', str(client).upper()])

        parameters['fields'] = ('kismet.device.base.macaddr', 'kismet.device.base.name')

        # payload = "json="+urllib.parse.quote_plus(json.dumps(parameters))
        payload = "json=" + json.dumps(parameters)
        _LOGGER.debug("Making request with this payload:" + payload)

        try:
            r = requests.post("http://" + self.server + ":" + str(self.port) + "/devices/last-time/" + "-" + str(
                self.scan_interval.total_seconds()) + "/devices.json",
                              headers={'Content-Type': 'application/x-www-form-urlencoded'},
                              data=payload,
                              auth=(self.user, self.password))

            now = dt_util.now()
            if r.ok:
                if r.json():
                    # we got a valid reply. Should look like this:
                    # [{'kismet.device.base.macaddr': 'AA:BB:CC:DD:EE:FF', 'kismet.device.base.name': 'My Device Name'}]
                    for pair in r.json():
                         _LOGGER.debug("Found device " + str(pair['kismet.device.base.macaddr']))
                         device = {}
                         device['name'] = pair['kismet.device.base.macaddr']
                         device['id'] = pair['kismet.device.base.macaddr']
                         
                         # parse location information (if any)
                         device['location'] = {}
                         if "dot11.probedssid.location" in pair and pair["dot11.probedssid.location"] != 0:
                             gps = pair["dot11.probedssid.gps"]
                         elif "dot11.advertisedssid.location" in pair and pair["dot11.advertisedssid.location"] != 0:
                             gps = pair["dot11.advertisedssid.location"]

                         if gps and "kismet.common.location.loc_valid" in gps and gps["kismet.common.location.loc_valid"] == 1:
                             # instead of delving further into the structure, we use the integer coordinates
                             device['location']['latitude'] = gps["kismet.common.location.avg_lat"] * .000001
                             device['location']['longitude'] = gps["kismet.common.location.avg_lon"] * .000001

                         self._update_device(device, device['id'])
                         last_results.append(device)
                else:
                     _LOGGER.error("Got an error in the kismet reply: " + r.text)
                     pass
            else:
                     _LOGGER.error(f"Got an error in the kismet query. Error code {r.status_code}, reply text {r.text}")
        except requests.exceptions.ConnectionError:
            _LOGGER.error("Error connecting to kismet instance")

        _LOGGER.info("Kismet scan finished")
