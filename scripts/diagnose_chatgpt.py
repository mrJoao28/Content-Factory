"""Explicit minimal real probe. Prints only safe transport diagnostics, never generated text."""

import argparse
import json
import logging

from factory.chatgpt import accounts
from factory.chatgpt_provider import ChatGPTProvider
from factory.schemas import AgentResult


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-plan-usage", action="store_true")
    args = parser.parse_args()
    if not args.confirm_plan_usage:
        parser.error("This real request consumes plan allowance. Pass --confirm-plan-usage to proceed.")
    # The application logger emits the same allowlisted diagnostic on protocol failures.
    logging.getLogger("factory.chatgpt_provider").addHandler(logging.NullHandler())
    provider = None
    try:
        provider = ChatGPTProvider(accounts, accounts.binding())
        provider.generate(
            "Creative Director",
            {
                "task": "Return a short connection check summary and an empty flags array. No project content is included."
            },
            AgentResult,
        )
    except Exception:
        details = provider.last_diagnostic if provider else None
        print(
            json.dumps(
                details
                or {
                    "http_status": None,
                    "content_type": None,
                    "request_id": None,
                    "error_code": "probe_unavailable",
                    "message": "No HTTP response was obtained. Check secure session access and connectivity from the same Windows user.",
                }
            )
        )
        return 1
    print(json.dumps(provider.last_diagnostic))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
