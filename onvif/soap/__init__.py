"""
SOAP helper utilities shared by device and media service handlers.
"""
import re
from typing import Optional


# Maps SOAPAction header values to short action names used in handler dispatch.
# ONVIF clients send the full URI; we extract just the local name.
_ACTION_PATTERN = re.compile(r"[/#](\w+)\"?$")


def parse_soap_action(soapaction_header: str) -> str:
    """
    Extract the operation name from a SOAPAction header value.

    Examples:
      '"http://www.onvif.org/ver10/device/wsdl/GetCapabilities"' -> 'GetCapabilities'
      'http://www.onvif.org/ver10/media/wsdl/GetProfiles'        -> 'GetProfiles'
    """
    header = soapaction_header.strip().strip('"')
    m = _ACTION_PATTERN.search(header)
    if m:
        return m.group(1)
    return header


def soap_envelope(body: str, action_ns: str = "") -> str:
    """Wrap a SOAP body fragment in a full SOAP 1.2 envelope."""
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tt="http://www.onvif.org/ver10/schema"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SOAP-ENV:Body>
{body}
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


def soap_fault(code: str, reason: str) -> str:
    """Return a SOAP fault envelope."""
    body = f"""\
    <SOAP-ENV:Fault>
      <SOAP-ENV:Code><SOAP-ENV:Value>{code}</SOAP-ENV:Value></SOAP-ENV:Code>
      <SOAP-ENV:Reason><SOAP-ENV:Text xml:lang="en">{reason}</SOAP-ENV:Text></SOAP-ENV:Reason>
    </SOAP-ENV:Fault>"""
    return soap_envelope(body)
