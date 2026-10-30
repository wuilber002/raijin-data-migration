"""Dedicated rollout entrypoint for the Raikou::Kai audit consumer."""

from app.component_worker import main
from app.audit_execution import run_once


if __name__ == "__main__":
    main(run_once)
