"""ssdp."""

import asyncio
import contextlib
import logging
import socket

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SSDPBroadcaster:
    """Class to handle SSDP broadcasting for Solar Manager."""

    def __init__(self, hass: HomeAssistant, interval: float = 5.0) -> None:
        """Initialize the SSDP broadcaster."""
        self.hass = hass
        self.interval = interval
        self._local_ip = None
        self._task = None
        self._transport = None
        self._sock = None

    async def get_local_ip(self) -> str:
        """Asynchronously get the local IP address."""

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
            _LOGGER.debug("Local IP address retrieved: %s", local_ip)
            return local_ip
        except Exception as e:
            _LOGGER.error("Failed to get local IP address: %s", e)
            return "0.0.0.0"

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

    async def broadcast_loop(self):
        """Broadcast SSDP messages at intervals."""
        ip_address = await self.get_local_ip()
        while True:
            await self.send_ssdp_broadcast(ip_address)
            await asyncio.sleep(self.interval)

    async def start(self):
        """Start the SSDP broadcasting task."""
        if self._task is None:
            self._task = self.hass.async_create_task(self.broadcast_loop())
            _LOGGER.info(
                "SSDP broadcaster started with interval %.2f seconds", self.interval
            )

    async def stop(self):
        """Stop the SSDP broadcasting task and clean up."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            _LOGGER.info("SSDP broadcaster stopped")

        if self._transport:
            self._transport.close()
            self._transport = None

        if self._sock:
            self._sock.close()
            self._sock = None

    async def async_cleanup(self):
        """Clean up resources."""
        await self.stop()
