"""Docker/OCI container operations — thin subprocess wrappers.

Pure subprocess wrappers. No agentrelay domain types — just strings.
All functions raise :class:`subprocess.CalledProcessError` on failure
unless documented otherwise.

Each function accepts a *runtime* parameter (default ``"docker"``) to
support alternative OCI runtimes such as Podman.
"""

from __future__ import annotations

import shlex
import subprocess


def is_available(runtime: str = "docker") -> bool:
    """Check whether the container runtime is available.

    Runs ``<runtime> info``.

    Returns:
        ``True`` if the runtime responds, ``False`` otherwise.
    """
    result = subprocess.run(
        [runtime, "info"],
        capture_output=True,
    )
    return result.returncode == 0


def image_exists(image: str, runtime: str = "docker") -> bool:
    """Check whether a container image exists locally.

    Runs ``<runtime> image inspect <image>``.

    Returns:
        ``True`` if the image exists, ``False`` otherwise.
    """
    result = subprocess.run(
        [runtime, "image", "inspect", image],
        capture_output=True,
    )
    return result.returncode == 0


def network_exists(name: str, runtime: str = "docker") -> bool:
    """Check whether a container network exists.

    Runs ``<runtime> network inspect <name>``.

    Returns:
        ``True`` if the network exists, ``False`` otherwise.
    """
    result = subprocess.run(
        [runtime, "network", "inspect", name],
        capture_output=True,
    )
    return result.returncode == 0


def network_create(name: str, runtime: str = "docker") -> None:
    """Create a container network.

    Runs ``<runtime> network create <name>``.
    """
    subprocess.run(
        [runtime, "network", "create", name],
        check=True,
        capture_output=True,
    )


def network_remove(name: str, runtime: str = "docker") -> None:
    """Remove a container network.

    Runs ``<runtime> network rm <name>``.
    """
    subprocess.run(
        [runtime, "network", "rm", name],
        check=True,
        capture_output=True,
    )


def stop(container_name: str, runtime: str = "docker") -> None:
    """Stop a running container.

    Runs ``<runtime> stop <name>``.
    """
    subprocess.run(
        [runtime, "stop", container_name],
        check=True,
        capture_output=True,
    )


def rm(container_name: str, runtime: str = "docker") -> None:
    """Remove a container.

    Runs ``<runtime> rm <name>``.
    """
    subprocess.run(
        [runtime, "rm", container_name],
        check=True,
        capture_output=True,
    )


def force_rm(container_name: str, runtime: str = "docker") -> None:
    """Force-remove a container (running or stopped).

    Runs ``<runtime> rm -f <name>``.
    """
    subprocess.run(
        [runtime, "rm", "-f", container_name],
        check=True,
        capture_output=True,
    )


def ps_by_label(label: str, runtime: str = "docker") -> list[str]:
    """List container names matching a label filter.

    Runs ``<runtime> ps -a --filter label=<label> --format '{{.Names}}'``.

    Args:
        label: Label filter string (e.g. ``"agentrelay.graph=mygraph"``).
        runtime: Container runtime binary name.

    Returns:
        List of container name strings (may be empty).
    """
    result = subprocess.run(
        [runtime, "ps", "-a", "--filter", f"label={label}", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [name for name in result.stdout.strip().split("\n") if name]


def build_run_command(
    container_name: str,
    image: str,
    cmd: str,
    *,
    volumes: list[tuple[str, str] | tuple[str, str, str]] | None = None,
    env_vars: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    network: str | None = None,
    workdir: str | None = None,
    runtime: str = "docker",
) -> str:
    """Build a ``docker run`` command string (not executed).

    Returns the full command as a string suitable for sending to a tmux
    pane.  Volumes are ``(src, dst)`` or ``(src, dst, opts)`` tuples
    where *opts* is e.g. ``"ro"``.

    Args:
        container_name: Name for the container (``--name``).
        image: Container image to run.
        cmd: Command string to execute inside the container.
        volumes: Bind mount specifications.
        env_vars: Environment variables to inject (``-e``).
        labels: Container labels to attach (``--label``).
        network: Docker network to attach (``--network``).
        workdir: Working directory inside the container (``-w``).
        runtime: Container runtime binary name.

    Returns:
        Complete command string.
    """
    parts: list[str] = [runtime, "run", "-it", "--rm", "--name", container_name]

    for vol in volumes or []:
        if len(vol) == 3:
            src, dst, opts = vol
            parts.extend(["-v", f"{src}:{dst}:{opts}"])
        else:
            src, dst = vol
            parts.extend(["-v", f"{src}:{dst}"])

    for key, value in (env_vars or {}).items():
        parts.extend(["-e", f"{key}={value}"])

    for key, value in (labels or {}).items():
        parts.extend(["--label", f"{key}={value}"])

    if network is not None:
        parts.extend(["--network", network])

    if workdir is not None:
        parts.extend(["-w", workdir])

    parts.append(image)
    parts.extend(["bash", "-c", cmd])

    return shlex.join(parts)
