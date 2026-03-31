"""
ONVIF Device Service SOAP handlers.

Handles: GetSystemDateAndTime, GetCapabilities, GetDeviceInformation,
         GetProfiles (proxied), GetVideoSources, GetScopes, GetServices.
"""
import os
import uuid
import datetime
from pathlib import Path
from fastapi.responses import Response

from . import soap_fault

TEMPLATES = Path(__file__).parent.parent / "templates"

_ONVIF_HOST = os.environ.get("ONVIF_HOST", "127.0.0.1")
_ONVIF_PORT = os.environ.get("ONVIF_PORT", "8080")
_DEVICE_NAME = os.environ.get("ONVIF_DEVICE_NAME", "Vivint Front Door")
_DEVICE_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _DEVICE_NAME))


def _xml_response(text: str) -> Response:
    return Response(content=text, media_type="application/soap+xml; charset=utf-8")


def _load(name: str, **kwargs) -> str:
    tmpl = (TEMPLATES / name).read_text()
    return tmpl.format(**kwargs) if kwargs else tmpl


# ── Handlers ──────────────────────────────────────────────────────────────────

def get_system_date_and_time() -> Response:
    now = datetime.datetime.now(datetime.timezone.utc)
    return _xml_response(_load(
        "date_time.xml",
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        year=now.year,
        month=now.month,
        day=now.day,
    ))


def get_capabilities() -> Response:
    return _xml_response(_load(
        "capabilities.xml",
        host=_ONVIF_HOST,
        port=_ONVIF_PORT,
    ))


def get_device_information() -> Response:
    return _xml_response(_load(
        "device_info.xml",
        device_uuid=_DEVICE_UUID,
    ))


def get_scopes() -> Response:
    body = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <tds:GetScopesResponse>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/type/video_encoder</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/type/audio_encoder</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/hardware/Vivint</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/name/{_DEVICE_NAME.replace(" ", "%20")}</tt:ScopeItem>
      </tds:Scopes>
    </tds:GetScopesResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


def get_services() -> Response:
    body = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <tds:GetServicesResponse>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>
        <tds:XAddr>http://{_ONVIF_HOST}:{_ONVIF_PORT}/onvif/device_service</tds:XAddr>
        <tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version>
      </tds:Service>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>
        <tds:XAddr>http://{_ONVIF_HOST}:{_ONVIF_PORT}/onvif/media_service</tds:XAddr>
        <tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version>
      </tds:Service>
    </tds:GetServicesResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


# ── Dispatch ──────────────────────────────────────────────────────────────────

_HANDLERS = {
    "GetSystemDateAndTime": get_system_date_and_time,
    "GetCapabilities": get_capabilities,
    "GetDeviceInformation": get_device_information,
    "GetScopes": get_scopes,
    "GetServices": get_services,
}


def handle(action: str, body: bytes) -> Response:
    handler = _HANDLERS.get(action)
    if handler:
        return handler()
    return Response(
        content=soap_fault("SOAP-ENV:Sender", f"Action not implemented: {action}"),
        status_code=501,
        media_type="application/soap+xml; charset=utf-8",
    )
