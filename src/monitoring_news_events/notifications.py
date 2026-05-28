from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .models import GeoConfig, GeoReport


class NotificationHub:
    def send(
        self,
        geo: GeoConfig,
        report: GeoReport,
        artifact_paths: dict[str, Path],
        report_url: str = "",
    ) -> list[str]:
        results: list[str] = []
        slack_url = os.getenv("SLACK_WEBHOOK_URL")
        if slack_url:
            destination = report_url or str(artifact_paths["markdown"])
            payload = {
                "text": (
                    f"Новый выпуск по GEO {geo.name} готов.\n"
                    f"Ссылка: {destination}"
                )
            }
            self._post_json(slack_url, payload)
            results.append("slack")

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            destination = report_url or str(artifact_paths["markdown"])
            payload = {
                "chat_id": telegram_chat_id,
                "text": (
                    f"Выпуск по GEO {geo.name} готов.\n"
                    f"Ссылка: {destination}"
                ),
            }
            self._post_json(url, payload)
            results.append("telegram")
        return results

    def _post_json(self, url: str, payload: dict) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20):
            return
