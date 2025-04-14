"""ssdp."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import socket

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

# Cache duration: 20 minutes
IP_CACHE_DURATION = timedelta(minutes=20)


class SSDPBroadcaster:
    """Class to handle SSDP broadcasting for Solar Manager."""

    def __init__(self, hass: HomeAssistant, interval: float = 5.0) -> None:
        """Initialize the SSDP broadcaster."""
        self.hass = hass
        self.interval = interval
        self._timer_remove: Callable[[], None] | None = None
        self._transport = None
        self._sock = None
        self._local_ip: str | None = None
        self._last_ip_fetch: datetime | None = None

    async def get_local_ip(self) -> str:
        """Asynchronously get the local IP address, using cache if available."""
        now = datetime.now()
        # Use cached IP if available and not expired
        if (
            self._local_ip is not None
            and self._last_ip_fetch is not None
            and now - self._last_ip_fetch < IP_CACHE_DURATION
        ):
            _LOGGER.debug("Using cached local IP address: %s", self._local_ip)
            return self._local_ip

        # Fetch new IP
        try:
            # Create a UDP socket to determine local IP
            loop = asyncio.get_running_loop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)

            # Connect to an external address to get local IP
            await loop.run_in_executor(None, lambda: sock.connect(("8.8.8.8", 80)))
            local_ip = sock.getsockname()[0]
            sock.close()
            self._local_ip = local_ip
            self._last_ip_fetch = now
            _LOGGER.debug("Local IP address retrieved: %s", local_ip)
        except Exception as e:
            _LOGGER.error("Failed to get local IP address: %s", e)
            self._local_ip = "0.0.0.0"
            self._last_ip_fetch = now
        return self._local_ip

    async def send_ssdp_broadcast(self, ip_address: str):
        """Send an SSDP broadcast message."""
        try:
            # Create UDP socket
            if not self._sock:
                self._sock = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
                )
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._sock.setblocking(False)

            # Create asyncio UDP transport
            if not self._transport:
                loop = asyncio.get_running_loop()
                self._transport, _ = await loop.create_datagram_endpoint(
                    lambda: asyncio.DatagramProtocol(), sock=self._sock
                )

            # Prepare and send SSDP message
            ssdp_message = f"maybetaken: mqtt://{ip_address}".encode()
            self._transport.sendto(ssdp_message, ("239.255.255.250", 1900))
        except Exception as e:
            _LOGGER.error("Failed to send SSDP broadcast: %s", e)

    async def broadcast_once(self, now=None) -> None:
        """Send a single SSDP broadcast."""
        ip_address = await self.get_local_ip()
        await self.send_ssdp_broadcast(ip_address)

    async def start(self):
        """Start the SSDP broadcasting timer."""
        if self._timer_remove is None:
            self._timer_remove = async_track_time_interval(
                self.hass, self.broadcast_once, timedelta(seconds=self.interval)
            )
            _LOGGER.info(
                "SSDP broadcaster started with interval %.2f seconds", self.interval
            )

    async def stop(self):
        """Stop the SSDP broadcasting timer and clean up."""
        if self._timer_remove:
            self._timer_remove()
            self._timer_remove = None

        if self._transport:
            self._transport.close()
            self._transport = None

        if self._sock:
            self._sock.close()
            self._sock = None

    async def async_cleanup(self):
        """Clean up resources."""
        await self.stop()
