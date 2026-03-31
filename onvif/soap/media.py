"""
ONVIF Media Service SOAP handlers.

Handles: GetProfiles, GetStreamUri, GetSnapshotUri, GetVideoSources,
         GetAudioSources, GetAudioOutputs, GetVideoSourceConfigurations.
"""
import os
import uuid
from pathlib import Path
from fastapi.responses import Response

from . import soap_fault

TEMPLATES = Path(__file__).parent.parent / "templates"

_ONVIF_HOST = os.environ.get("ONVIF_HOST", "127.0.0.1")
_ONVIF_PORT = os.environ.get("ONVIF_PORT", "8080")
_DEVICE_NAME = os.environ.get("ONVIF_DEVICE_NAME", "Vivint Front Door")
_DEVICE_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _DEVICE_NAME))

_HA_BASE_URL = os.environ.get("HA_BASE_URL", "")
_HA_TOKEN = os.environ.get("HA_TOKEN", "")
_HA_CAMERA_ENTITY = os.environ.get("HA_CAMERA_ENTITY", "camera.vivint_front_door")

_RTSP_HOST = os.environ.get("ONVIF_HOST", "127.0.0.1")
_RTSP_PORT = os.environ.get("RTSP_PORT", "8554")
_STREAM_NAME = os.environ.get("ONVIF_STREAM_NAME", "vivint_front")

# Default resolution — Vivint cameras are typically 1080p or 720p
_WIDTH = int(os.environ.get("CAMERA_WIDTH", "1280"))
_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "720"))


def _xml_response(text: str) -> Response:
    return Response(content=text, media_type="application/soap+xml; charset=utf-8")


def _load(name: str, **kwargs) -> str:
    tmpl = (TEMPLATES / name).read_text()
    return tmpl.format(**kwargs) if kwargs else tmpl


# ── Handlers ──────────────────────────────────────────────────────────────────

def get_profiles() -> Response:
    return _xml_response(_load(
        "profiles.xml",
        device_name=_DEVICE_NAME,
        width=_WIDTH,
        height=_HEIGHT,
    ))


def get_video_sources() -> Response:
    body = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <trt:GetVideoSourcesResponse>
      <trt:VideoSources token="VideoSource_1">
        <tt:Framerate>15</tt:Framerate>
        <tt:Resolution>
          <tt:Width>{_WIDTH}</tt:Width>
          <tt:Height>{_HEIGHT}</tt:Height>
        </tt:Resolution>
      </trt:VideoSources>
    </trt:GetVideoSourcesResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


def get_audio_sources() -> Response:
    body = """\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <trt:GetAudioSourcesResponse>
      <trt:AudioSources token="AudioSource_1">
        <tt:Channels>1</tt:Channels>
      </trt:AudioSources>
    </trt:GetAudioSourcesResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


def get_audio_outputs() -> Response:
    body = """\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <trt:GetAudioOutputsResponse>
      <trt:AudioOutputs token="AudioOutput_1">
      </trt:AudioOutputs>
    </trt:GetAudioOutputsResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


def get_stream_uri() -> Response:
    stream_uri = f"rtsp://{_RTSP_HOST}:{_RTSP_PORT}/{_STREAM_NAME}"
    return _xml_response(_load("stream_uri.xml", stream_uri=stream_uri))


def get_snapshot_uri() -> Response:
    if _HA_BASE_URL and _HA_TOKEN:
        snapshot_uri = (
            f"{_HA_BASE_URL}/api/camera_proxy/{_HA_CAMERA_ENTITY}"
            f"?access_token={_HA_TOKEN}"
        )
    else:
        snapshot_uri = f"http://{_ONVIF_HOST}:{_ONVIF_PORT}/snapshot"
    return _xml_response(_load("snapshot_uri.xml", snapshot_uri=snapshot_uri))


def get_video_source_configurations() -> Response:
    body = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <SOAP-ENV:Body>
    <trt:GetVideoSourceConfigurationsResponse>
      <trt:Configurations token="VideoSource_1">
        <tt:Name>VideoSource</tt:Name>
        <tt:UseCount>1</tt:UseCount>
        <tt:SourceToken>VideoSource_1</tt:SourceToken>
        <tt:Bounds x="0" y="0" width="{_WIDTH}" height="{_HEIGHT}"/>
      </trt:Configurations>
    </trt:GetVideoSourceConfigurationsResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return _xml_response(body)


# ── Dispatch ──────────────────────────────────────────────────────────────────

_HANDLERS = {
    "GetProfiles": get_profiles,
    "GetVideoSources": get_video_sources,
    "GetAudioSources": get_audio_sources,
    "GetAudioOutputs": get_audio_outputs,
    "GetStreamUri": get_stream_uri,
    "GetSnapshotUri": get_snapshot_uri,
    "GetVideoSourceConfigurations": get_video_source_configurations,
    # Profile S / T compat aliases
    "GetProfile": get_profiles,
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
