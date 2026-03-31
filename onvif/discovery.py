"""
WS-Discovery responder for ONVIF device discovery.

Listens on the WS-Discovery multicast group (239.255.255.250:3702) and
responds to Probe messages so that Home Assistant and other ONVIF clients
can auto-discover this device on the local network.

Run as a daemon thread from main.py's lifespan handler.
"""
import socket
import struct
import uuid
import logging
import os
import re

log = logging.getLogger(__name__)

MCAST_GRP = "239.255.255.250"
MCAST_PORT = 3702

ONVIF_PORT = int(os.environ.get("ONVIF_PORT", "8080"))

# Namespaces required for WS-Discovery
NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "dn": "http://www.onvif.org/ver10/network/wsdl",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
}

PROBE_MATCH_TMPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
  xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
    <a:MessageID>urn:uuid:{msg_id}</a:MessageID>
    <a:RelatesTo>{relates_to}</a:RelatesTo>
    <a:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <a:EndpointReference>
          <a:Address>urn:uuid:{device_uuid}</a:Address>
        </a:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>
          onvif://www.onvif.org/type/video_encoder
          onvif://www.onvif.org/type/audio_encoder
          onvif://www.onvif.org/hardware/Vivint
          onvif://www.onvif.org/name/{device_name}
          onvif://www.onvif.org/location/
        </d:Scopes>
        <d:XAddrs>http://{host}:{port}/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>"""

# Stable UUID for this device instance (generated once, reused across restarts
# because it's derived from the device name env var)
_DEVICE_NAME = os.environ.get("ONVIF_DEVICE_NAME", "Vivint Front Door")
DEVICE_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _DEVICE_NAME))


def _get_local_ip() -> str:
    """Best-effort: find the LAN IP of this container/host."""
    explicit = os.environ.get("ONVIF_HOST", "")
    if explicit:
        return explicit
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _extract_message_id(data: bytes) -> str:
    """Pull the wsa:MessageID value out of the Probe XML."""
    try:
        text = data.decode("utf-8", errors="replace")
        m = re.search(r"<[^>]*MessageID[^>]*>([^<]+)<", text)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return "urn:uuid:" + str(uuid.uuid4())


def run() -> None:
    """
    Block forever, serving WS-Discovery probes.
    Call from a daemon thread so it doesn't prevent process exit.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass  # Not available on all platforms

    sock.bind(("", MCAST_PORT))

    mreq = struct.pack(
        "4sL", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    log.info(
        "WS-Discovery listening on %s:%d (device uuid=%s)",
        MCAST_GRP, MCAST_PORT, DEVICE_UUID,
    )

    device_name_encoded = _DEVICE_NAME.replace(" ", "%20")

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except OSError as exc:
            log.warning("WS-Discovery recv error: %s", exc)
            continue

        if b"Probe" not in data:
            continue

        host = _get_local_ip()
        relates_to = _extract_message_id(data)
        response = PROBE_MATCH_TMPL.format(
            msg_id=uuid.uuid4(),
            relates_to=relates_to,
            device_uuid=DEVICE_UUID,
            device_name=device_name_encoded,
            host=host,
            port=ONVIF_PORT,
        ).encode("utf-8")

        try:
            sock.sendto(response, addr)
            log.debug("Sent ProbeMatch to %s", addr)
        except OSError as exc:
            log.warning("WS-Discovery send error: %s", exc)
