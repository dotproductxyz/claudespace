"""Docker and Docker Compose utilities."""

import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import docker
import docker.errors
import yaml
from rich.console import Console

from .exceptions import DockerError

console = Console()


class PortAllocator:
    """Allocate unique ports for services."""

    BASE_PORT = 15000

    def __init__(self):
        self.client = docker.from_env()
        self._used_ports = self._get_used_ports()

    def _get_used_ports(self) -> set[int]:
        """Get all ports currently in use by Docker containers."""
        used: set[int] = set()
        for container in self.client.containers.list():
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            for port_bindings in ports.values():
                if port_bindings:
                    for binding in port_bindings:
                        if isinstance(binding, dict) and "HostPort" in binding:
                            used.add(int(binding["HostPort"]))
        return used

    def allocate_port(self, preferred_port: int) -> int:
        """Allocate a new port, starting from BASE_PORT."""
        port = self.BASE_PORT
        while port in self._used_ports or self._is_port_in_use(port):
            port += 1
        self._used_ports.add(port)
        return port

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use on the system."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return False
            except OSError:
                return True


class DockerComposeManager:
    """Manage Docker Compose for a workspace."""

    def __init__(self, workspace_path: Path, project_name: str):
        self.workspace_path = workspace_path
        self.project_name = project_name
        # Check for both .yml and .yaml extensions
        yml_file = workspace_path / "docker-compose.yml"
        yaml_file = workspace_path / "docker-compose.yaml"
        if yaml_file.exists():
            self.compose_file = yaml_file
        else:
            self.compose_file = yml_file  # Default to .yml for error messages
        self.override_file = workspace_path / "docker-compose.override.yml"
        self.port_mappings: dict[str, tuple[int, int]] = {}

    def create_override(self, services: dict[str, Any]):
        """Create docker-compose.override.yml with new ports."""
        if not self.compose_file.exists():
            raise DockerError(f"Docker Compose file not found: {self.compose_file}")

        # Parse original compose file
        with open(self.compose_file) as f:
            compose_data = yaml.safe_load(f)

        if not compose_data or "services" not in compose_data:
            console.print("[yellow]Warning: No services found in docker-compose.yml[/yellow]")
            return

        # Create override with new ports
        override: dict[str, Any] = {"version": compose_data.get("version", "3"), "services": {}}
        allocator = PortAllocator()

        for service_name, service_data in compose_data["services"].items():
            if service_name not in services:
                continue

            ports = service_data.get("ports", [])
            if not ports:
                continue

            new_ports: list[str] = []
            for port_spec in ports:
                if isinstance(port_spec, str):
                    # Parse port specification (e.g., "5432:5432" or "5432")
                    parts = port_spec.split(":")
                    if len(parts) == 2:
                        host_port, container_port = parts
                        old_port = int(host_port)
                        new_port = allocator.allocate_port(old_port)
                        new_ports.append(f"{new_port}:{container_port}")
                        self.port_mappings[service_name] = (old_port, new_port)
                    else:
                        # Single port number
                        old_port = int(parts[0])
                        new_port = allocator.allocate_port(old_port)
                        new_ports.append(f"{new_port}:{old_port}")
                        self.port_mappings[service_name] = (old_port, new_port)

            if new_ports:
                override["services"][service_name] = {"ports": new_ports}

        # Write override file
        with open(self.override_file, "w") as f:
            yaml.dump(override, f)

    def up(self):
        """Start Docker Compose services."""
        cmd = ["docker", "compose", "-p", self.project_name, "-f", str(self.compose_file)]

        if self.override_file.exists():
            cmd.extend(["-f", str(self.override_file)])

        cmd.extend(["up", "-d"])

        subprocess.run(cmd, cwd=self.workspace_path, check=True)

    def down(self, volumes: bool = False):
        """Stop Docker Compose services."""
        # If compose file doesn't exist, try to stop by project name only
        if not self.compose_file.exists():
            cmd = ["docker", "compose", "-p", self.project_name, "down"]
            if volumes:
                cmd.append("-v")
            # Don't check return code as project might not exist
            subprocess.run(cmd, cwd=self.workspace_path, capture_output=True)
            return

        cmd = ["docker", "compose", "-p", self.project_name, "-f", str(self.compose_file)]

        if self.override_file.exists():
            cmd.extend(["-f", str(self.override_file)])

        cmd.append("down")

        if volumes:
            cmd.append("-v")

        subprocess.run(cmd, cwd=self.workspace_path, check=True)

    def is_running(self) -> bool:
        """Check if services are running."""
        # If compose file doesn't exist, workspace can't be running
        if not self.compose_file.exists():
            return False

        cmd = [
            "docker",
            "compose",
            "-p",
            self.project_name,
            "-f",
            str(self.compose_file),
            "ps",
            "-q",
        ]

        result = subprocess.run(cmd, cwd=self.workspace_path, capture_output=True, text=True)

        return bool(result.stdout.strip())

    def wait_for_service(self, service_name: str, timeout: int = 60):
        """Wait for a service to be healthy."""
        client = docker.from_env()
        container_name = f"{self.project_name}_{service_name}_1"

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                container = client.containers.get(container_name)
                if container.status == "running":
                    # Check if service has health check
                    if "Health" in container.attrs["State"]:
                        health = container.attrs["State"]["Health"]["Status"]
                        if health == "healthy":
                            return
                    else:
                        # No health check, just check if running
                        return
            except docker.errors.NotFound:
                pass

            time.sleep(1)

        raise TimeoutError(f"Service {service_name} did not become healthy in {timeout}s")
