"""Dedicated rollout entrypoint for the Raikou::Sei restore consumer."""

from app.component_worker import main
from app.restore_execution import run_once


if __name__ == "__main__":
    main(run_once)
