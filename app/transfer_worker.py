"""Dedicated rollout entrypoint for the Raiju transfer consumer."""

from app.component_worker import main
from app.transfer_execution import run_once


if __name__ == "__main__":
    main(run_once)
