"""Dedicated rollout entrypoint for the Raikou::Kō discovery consumer."""

from app.component_worker import main
from app.discovery_execution import run_once


if __name__ == "__main__":
    main(run_once)
