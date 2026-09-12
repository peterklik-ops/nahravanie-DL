"""
Jednorazový skript: získa Allegro refresh token cez OAuth2 Device Flow.

Spustite raz pred prvým behom stock_sync.py (z priečinka agent/, s
aktivovaným venv a vyplneným ALLEGRO_CLIENT_ID/ALLEGRO_CLIENT_SECRET v .env):

    python allegro_device_login.py

Skript vypíše URL a kód - otvorte URL v prehliadači, prihláste sa ako
predajca (účet, ktorého ponuky sa majú spravovať) a potvrďte prístup
aplikácii. Skript následne uloží access aj refresh token do
config.ALLEGRO_TOKEN_STORE (`allegro.py` ho potom sám priebežne obnovuje).
"""

import time

import requests

import config
from allegro import _basic_auth_header, _save_token_store


def main() -> None:
    response = requests.post(
        f"{config.ALLEGRO_AUTH_URL}/device",
        headers=_basic_auth_header(),
        data={"client_id": config.ALLEGRO_CLIENT_ID},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    verification_uri = payload.get("verification_uri_complete") or payload["verification_uri"]
    print(f"1. Otvorte v prehliadači: {verification_uri}")
    if not payload.get("verification_uri_complete"):
        print(f"   a zadajte kód: {payload['user_code']}")
    print("2. Prihláste sa ako predajca a potvrďte prístup aplikácii.")
    print("Čakám na potvrdenie...")

    interval = payload.get("interval", 5)
    deadline = time.time() + payload.get("expires_in", 600)

    while time.time() < deadline:
        time.sleep(interval)
        token_response = requests.post(
            f"{config.ALLEGRO_AUTH_URL}/token",
            headers=_basic_auth_header(),
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": payload["device_code"],
            },
            timeout=30,
        )
        if token_response.status_code == 200:
            token_payload = token_response.json()
            _save_token_store(
                {
                    "access_token": token_payload["access_token"],
                    "refresh_token": token_payload["refresh_token"],
                    "obtained_at": time.time(),
                }
            )
            print(f"Hotovo. Token uložený do: {config.ALLEGRO_TOKEN_STORE}")
            return

        error = token_response.json().get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue

        token_response.raise_for_status()

    raise TimeoutError("Vypršal čas na potvrdenie prihlásenia (expires_in).")


if __name__ == "__main__":
    main()
