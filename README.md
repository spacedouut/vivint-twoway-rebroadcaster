# vivint-twoway-rebroadcaster

Bridges a Vivint smart doorbell into a standard RTSP/ONVIF camera that works
with Frigate and Home Assistant — including two-way audio.

## Architecture

```
[Vivint Doorbell]
  ├─ Video: MJPEG via Home Assistant camera proxy
  └─ Audio: SIP over WebSocket (WSS)
         │                       │
      FFmpeg                 Asterisk
   (pull MJPEG)          (WSS SIP endpoint)
         │                       │
         └──────── go2rtc ────────┘
              (mux video + RTP audio)
                       │
           RTSP + WebRTC + HLS + backchannel
                       │
          Python ONVIF wrapper (this repo)
          (WS-Discovery + SOAP façade)
                       │
           Frigate / Home Assistant
```

## Requirements

- Docker & Docker Compose v2
- A running Home Assistant instance with the Vivint integration
- SIP credentials for the doorbell (found in the Vivint HA card config or
  captured from browser network traffic)

## Quick Start

```bash
# 1. Copy and fill in credentials
cp .env.example .env
nano .env          # Fill in HA_TOKEN, SIP_* vars, ONVIF_HOST

# 2. Start everything
make up            # or: docker compose up -d

# 3. Check status
make status

# 4. Test the RTSP stream
make rtsp-test     # requires ffplay
```

## Configuration

All settings live in `.env` (copy from `.env.example`):

| Variable | Description |
|----------|-------------|
| `HA_BASE_URL` | Home Assistant URL, e.g. `http://homeassistant.local:8123` |
| `HA_TOKEN` | Long-lived access token (HA → Profile → Security → Long-Lived Access Tokens) |
| `HA_CAMERA_ENTITY` | Entity ID of the Vivint camera in HA, e.g. `camera.vivint_front_door` |
| `HA_WEBHOOK_ID` | Webhook ID to fire on doorbell press (create in HA Automations) |
| `SIP_WSS_URL` | WebSocket SIP server URL, e.g. `wss://sip.vivintsky.com:443` |
| `SIP_SERVER` | SIP server hostname |
| `SIP_USERNAME` | Your SIP username |
| `SIP_PASSWORD` | Your SIP password |
| `SIP_DOORBELL_USERNAME` | Doorbell's SIP username/extension |
| `SIP_DOORBELL_DOMAIN` | Doorbell's SIP domain |
| `ONVIF_HOST` | **LAN IP of this Docker host** (used in stream URLs returned to Frigate/HA) |
| `ONVIF_DEVICE_NAME` | Display name shown in ONVIF clients (default: `Vivint Front Door`) |
| `ONVIF_STREAM_NAME` | go2rtc stream name (default: `vivint_front`) |
| `RTSP_PORT` | RTSP port (default: `8554`) |
| `GO2RTC_PORT` | go2rtc API port (default: `1984`) |

> **Token note**: Use a *long-lived* HA access token, not the camera proxy token
> visible in the browser. Long-lived tokens don't expire.

## Integrating with Home Assistant

### Generic Camera (direct RTSP)

```yaml
# configuration.yaml
camera:
  - platform: generic
    name: Vivint Front Door
    stream_source: rtsp://YOUR_DOCKER_HOST_IP:8554/vivint_front
    still_image_url: http://YOUR_DOCKER_HOST_IP:8080/snapshot
```

### ONVIF Integration (auto-discovery)

1. HA Settings → Devices & Services → Add Integration → ONVIF
2. It should auto-discover "Vivint Front Door" via WS-Discovery
3. If not, enter manually: Host = `YOUR_DOCKER_HOST_IP`, Port = `8080`
4. Username/password: leave blank (auth not implemented — local network only)

### Frigate

```yaml
# frigate config.yml
cameras:
  vivint_front_door:
    ffmpeg:
      inputs:
        - path: rtsp://YOUR_DOCKER_HOST_IP:8554/vivint_front
          roles:
            - detect
            - record
    detect:
      width: 1280
      height: 720
      fps: 15
```

### Two-Way Audio (WebRTC)

Open `http://YOUR_DOCKER_HOST_IP:1984` in a browser. go2rtc's built-in WebRTC
UI lets you view the stream and send backchannel audio to the doorbell.

For HA dashboard cards, use the go2rtc WebRTC card:
```yaml
type: custom:webrtc-camera
url: rtsp://YOUR_DOCKER_HOST_IP:8554/vivint_front
```

### Doorbell Press Automation

When the doorbell button is pressed, Asterisk fires a webhook to HA.
Create a webhook-triggered automation in HA:

1. Trigger: Webhook → ID matches `HA_WEBHOOK_ID` in your `.env`
2. Action: Notification, light flash, etc.

## Troubleshooting

**go2rtc stream offline**
```bash
make logs-go2rtc
# Check that HA_BASE_URL, HA_TOKEN, and HA_CAMERA_ENTITY are correct
curl -H "Authorization: Bearer $HA_TOKEN" $HA_BASE_URL/api/camera_proxy/$HA_CAMERA_ENTITY
```

**Asterisk not registering**
```bash
make logs-asterisk
# Check SIP_* credentials; verify SIP_WSS_URL is reachable from Docker host
```

**ONVIF not discovered**
```bash
make onvif-probe
# The onvif service uses network_mode: host — verify ONVIF_HOST matches the host LAN IP
```

**Two-way audio not working**
- Confirm Asterisk is registered to the SIP server (`make logs-asterisk`)
- The backchannel RTP path (go2rtc port 5005 → Asterisk EAGI bridge) is the
  most complex part; check both container logs when initiating a talk session

## Services & Ports

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Asterisk | 5061 | TCP/WSS | SIP over WebSocket |
| Asterisk | 10000-10100 | UDP | RTP media |
| go2rtc | 1984 | TCP/HTTP | API, WebRTC, HLS |
| go2rtc | 8554 | TCP/RTSP | RTSP streams |
| go2rtc | 5004 | UDP/RTP | Audio in from Asterisk |
| go2rtc | 5005 | UDP/RTP | Backchannel audio out |
| onvif | 8080 | TCP/HTTP | ONVIF SOAP |
| onvif | 3702 | UDP/Multicast | WS-Discovery |

## File Structure

```
.
├── docker-compose.yml
├── .env.example
├── go2rtc.yaml
├── Makefile
├── asterisk/
│   ├── etc/asterisk/          # Config templates (envsubst applied at startup)
│   │   ├── asterisk.conf
│   │   ├── modules.conf
│   │   ├── pjsip.conf
│   │   ├── extensions.conf
│   │   ├── rtp.conf
│   │   └── docker-entrypoint.sh
│   └── agi-bin/               # AGI scripts copied into container at startup
│       ├── notify_ha.agi      # Fires HA webhook on doorbell press
│       └── bridge_rtp.agi     # Bridges SIP audio <-> go2rtc RTP
└── onvif/
    ├── Dockerfile
    ├── main.py                # FastAPI app
    ├── discovery.py           # WS-Discovery multicast responder
    ├── soap/
    │   ├── __init__.py        # parse_soap_action helper
    │   ├── device.py          # Device service handlers
    │   └── media.py           # Media service handlers
    └── templates/             # SOAP XML response templates
        ├── capabilities.xml
        ├── date_time.xml
        ├── device_info.xml
        ├── device_service.xml
        ├── profiles.xml
        ├── snapshot_uri.xml
        └── stream_uri.xml
```

## License

MIT
