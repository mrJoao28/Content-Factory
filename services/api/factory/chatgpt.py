"""One local ChatGPT session service; no CLI, SDK subprocess or API key."""

from .chatgpt_accounts import ChatGPTAccounts
from .chatgpt_auth import ChatGPTLogin

accounts = ChatGPTAccounts()
login = ChatGPTLogin(accounts)


def close():
    login.cancel()
