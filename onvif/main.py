"""
Vivint Doorbell ONVIF Bridge — FastAPI application.

Exposes:
  POST /onvif/device_service  — ONVIF Device Service (SOAP)
  GET  /onvif/device_service  — WSDL stub
  POST /onvif/media_service   — ONVIF Media Service (SOAP)
  GET  /onvif/media_service   — WSDL stub
  GET  /health                — go2rtc stream status
  GET  /snapshot              — proxy snapshot from HA (fallback)

WS-Discovery runs as a background daemon thread for LAN auto-discovery.
"""
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse

import discovery
from soap import parse_soap_action
import soap.device as device_svc
import soap.media as media_svc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("onvif")

TEMPLATES = Path(__file__).parent / "templates"

_ONVIF_HOST = os.environ.get("ONVIF_HOST", "127.0.0.1")
_ONVIF_PORT = os.environ.get("ONVIF_PORT", "8080")
_GO2RTC_URL = os.environ.get("GO2RTC_URL", "http://localhost:1984")
_HA_BASE_URL = os.environ.get("HA_BASE_URL", "")
_HA_TOKEN = os.environ.get("HA_TOKEN", "")
_HA_CAMERA_ENTITY = os.environ.get("HA_CAMERA_ENTITY", "camera.vivint_front_door")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start WS-Discovery in a daemon thread so it doesn't block shutdown
    t = threading.Thread(target=discovery.run, name="ws-discovery", daemon=True)
    t.start()
    log.info(
        "ONVIF bridge started — device service at http://%s:%s/onvif/device_service",
        _ONVIF_HOST, _ONVIF_PORT,
    )
    yield
    log.info("ONVIF bridge shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Vivint ONVIF Bridge", lifespan=lifespan)


# ── Device Service ────────────────────────────────────────────────────────────

@app.get("/onvif/device_service")
async def device_service_wsdl():
    tmpl = (TEMPLATES / "device_service.xml").read_text()
    xml = tmpl.format(host=_ONVIF_HOST, port=_ONVIF_PORT)
    return Response(content=xml, media_type="text/xml; charset=utf-8")


@app.post("/onvif/device_service")
async def device_service(request: Request):
    body = await request.body()
    soapaction = request.headers.get("soapaction", "")
    action = parse_soap_action(soapaction)
    log.debug("device_service action=%s", action)
    return device_svc.handle(action, body)


# ── Media Service ─────────────────────────────────────────────────────────────

@app.get("/onvif/media_service")
async def media_service_wsdl():
    # Return a minimal service description on GET
    xml = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             name="MediaService"
             targetNamespace="http://www.onvif.org/ver10/media/wsdl">
  <service name="MediaService">
    <port name="MediaPort">
      <soap:address xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                    location="http://{_ONVIF_HOST}:{_ONVIF_PORT}/onvif/media_service"/>
    </port>
  </service>
</definitions>"""
    return Response(content=xml, media_type="text/xml; charset=utf-8")


@app.post("/onvif/media_service")
async def media_service(request: Request):
    body = await request.body()
    soapaction = request.headers.get("soapaction", "")
    action = parse_soap_action(soapaction)
    log.debug("media_service action=%s", action)
    return media_svc.handle(action, body)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Returns go2rtc stream status. 200 = at least one stream is online."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_GO2RTC_URL}/api/streams")
        streams = r.json()
        stream_name = os.environ.get("ONVIF_STREAM_NAME", "vivint_front")
        ok = stream_name in streams
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ok" if ok else "stream_offline", "streams": streams},
        )
    except Exception as exc:
        log.warning("health check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "go2rtc_unreachable", "error": str(exc)})


# ── Snapshot proxy ────────────────────────────────────────────────────────────

@app.get("/snapshot")
async def snapshot():
    """Proxy a JPEG snapshot from Home Assistant."""
    if not _HA_BASE_URL or not _HA_TOKEN:
        return Response(status_code=503, content="HA not configured")
    url = f"{_HA_BASE_URL}/api/camera_proxy/{_HA_CAMERA_ENTITY}"
    headers = {"Authorization": f"Bearer {_HA_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
        return Response(content=r.content, media_type=r.headers.get("content-type", "image/jpeg"))
    except Exception as exc:
        log.warning("snapshot proxy failed: %s", exc)
        return Response(status_code=502, content=str(exc))
