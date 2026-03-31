.PHONY: up down logs status restart build clean

# ── Lifecycle ─────────────────────────────────────────────────────────────────

up:
	@cp -n .env.example .env 2>/dev/null && echo "Created .env from .env.example — edit it before continuing!" || true
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose build --no-cache onvif

logs:
	docker compose logs -f

logs-asterisk:
	docker compose logs -f asterisk

logs-go2rtc:
	docker compose logs -f go2rtc

logs-onvif:
	docker compose logs -f onvif

# ── Status / debug ────────────────────────────────────────────────────────────

status:
	@echo "=== go2rtc streams ==="
	@curl -sf http://localhost:$${GO2RTC_PORT:-1984}/api/streams 2>/dev/null | python3 -m json.tool || echo "(go2rtc not reachable)"
	@echo ""
	@echo "=== ONVIF health ==="
	@curl -sf http://localhost:$${ONVIF_PORT:-8080}/health 2>/dev/null | python3 -m json.tool || echo "(onvif not reachable)"

rtsp-test:
	@echo "Testing RTSP stream — press Ctrl+C to stop"
	ffplay -fflags nobuffer -flags low_delay -i rtsp://localhost:$${RTSP_PORT:-8554}/$${ONVIF_STREAM_NAME:-vivint_front}

onvif-probe:
	@echo "Probing ONVIF device service..."
	@curl -sf -X POST http://localhost:$${ONVIF_PORT:-8080}/onvif/device_service \
	  -H 'Content-Type: application/soap+xml' \
	  -H 'SOAPAction: "http://www.onvif.org/ver10/device/wsdl/GetCapabilities"' \
	  -d '<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>' \
	  | python3 -c "import sys; import xml.dom.minidom; print(xml.dom.minidom.parseString(sys.stdin.read()).toprettyxml(indent='  '))"

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	docker compose down -v --remove-orphans
	docker image rm vivint-twoway-rebroadcaster-onvif 2>/dev/null || true
