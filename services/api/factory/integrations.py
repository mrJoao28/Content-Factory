"""Real OAuth and official HTTP APIs. No mock implementation or credential extraction."""
import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import select

from .config import settings
from .db import Session
from .models import PlatformConnection, UserSettings
from .security import ConfigurationRequired, Vault

GOOGLE_SCOPES = {
    "google": ["https://www.googleapis.com/auth/drive.file"],
    "youtube": ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"],
}


class PlatformError(RuntimeError):
    def __init__(self, service, status=0, code="request_failed"):
        super().__init__(f"{service}: {code} (HTTP {status}); see integration setup/quotas")
        self.status = status
        self.code = code


class OAuth:
    def __init__(self, client=None, vault=None):
        self.client = client or httpx.Client(timeout=60)
        self.vault = vault or Vault()

    def start(self, platform):
        if platform not in {"google", "youtube", "tiktok"}:
            raise ValueError("Unsupported platform")
        if platform == "tiktok":
            if not settings.tiktok_client_key or not settings.tiktok_client_secret:
                raise ConfigurationRequired("Configure TikTok client key/secret and registered HTTPS redirect URI")
            redirect = urlparse(settings.tiktok_redirect_uri)
            if redirect.scheme != "https" or not redirect.hostname or redirect.query or redirect.fragment:
                raise ConfigurationRequired("TikTok Web Login requires a registered static HTTPS callback; see docs/TIKTOK_SETUP.md")
        elif not settings.google_client_id or not settings.google_client_secret:
            raise ConfigurationRequired("Configure Google OAuth web client ID, secret and loopback redirect URI")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state_id = "oauth-"+hashlib.sha256(state.encode()).hexdigest()
        with Session.begin() as db:
            db.add(UserSettings(id=state_id, values={"platform": platform, "expires": time.time()+600,
                                                   "verifier": verifier}))
        if platform == "tiktok":
            params = {"client_key": settings.tiktok_client_key, "response_type": "code",
                      "scope": "user.info.basic,video.upload"+(",video.publish" if settings.tiktok_direct_post_enabled else ""), "redirect_uri": settings.tiktok_redirect_uri,
                      "state": state}
            return "https://www.tiktok.com/v2/auth/authorize/?"+urlencode(params)
        params = {"client_id": settings.google_client_id, "redirect_uri": settings.google_redirect_uri,
                  "response_type": "code", "scope": " ".join(GOOGLE_SCOPES[platform]), "state": state,
                  "access_type": "offline", "prompt": "consent", "code_challenge": challenge,
                  "code_challenge_method": "S256"}
        return "https://accounts.google.com/o/oauth2/v2/auth?"+urlencode(params)

    def complete(self, state, code, expected=None):
        with Session.begin() as db:
            row = db.get(UserSettings, "oauth-"+hashlib.sha256(state.encode()).hexdigest())
            if not row or row.values["expires"] < time.time():
                raise ValueError("Invalid or expired OAuth state")
            value = row.values
            if expected and value["platform"] not in ({expected} if isinstance(expected, str) else expected):
                raise ValueError("OAuth provider mismatch")
            db.delete(row)  # Single use, including failed exchanges.
        platform = value["platform"]
        if platform == "tiktok":
            url = "https://open.tiktokapis.com/v2/oauth/token/"
            body = {"client_key": settings.tiktok_client_key, "client_secret": settings.tiktok_client_secret,
                    "code": code, "grant_type": "authorization_code", "redirect_uri": settings.tiktok_redirect_uri}
        else:
            url = "https://oauth2.googleapis.com/token"
            body = {"client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                    "code": code, "grant_type": "authorization_code", "redirect_uri": settings.google_redirect_uri,
                    "code_verifier": value["verifier"]}
        response = self.client.post(url, data=body)
        if not response.is_success:
            raise PlatformError(platform, response.status_code, "oauth_exchange_failed")
        token = response.json()
        if not token.get("access_token"):
            raise PlatformError(platform, response.status_code, "missing_access_token")
        token["expires_at"] = time.time()+token.get("expires_in", 3600)
        self.vault.put(platform, token)
        with Session.begin() as db:
            connection = db.scalar(select(PlatformConnection).where(PlatformConnection.platform == platform))
            if not connection:
                connection = PlatformConnection(platform=platform)
                db.add(connection)
            connection.status = "CONNECTED"
            connection.scopes = token.get("scope", "").replace(",", " ").split()
            connection.account_id = token.get("open_id", "")
        return platform

    def token(self, platform):
        token = self.vault.get(platform)
        if not token:
            raise ConfigurationRequired(f"{platform}: authentication required")
        if token.get("expires_at", 0) <= time.time()+60:
            if not token.get("refresh_token"):
                raise ConfigurationRequired(f"{platform}: authentication expired; reconnect")
            if platform == "tiktok":
                url = "https://open.tiktokapis.com/v2/oauth/token/"
                body = {"client_key": settings.tiktok_client_key, "client_secret": settings.tiktok_client_secret}
            else:
                url = "https://oauth2.googleapis.com/token"
                body = {"client_id": settings.google_client_id, "client_secret": settings.google_client_secret}
            response = self.client.post(url, data={**body, "grant_type": "refresh_token",
                                                   "refresh_token": token["refresh_token"]})
            if not response.is_success or not response.json().get("access_token"):
                raise ConfigurationRequired(f"{platform}: authentication expired; reconnect")
            token = {**token, **response.json()}
            token["expires_at"] = time.time()+response.json().get("expires_in", 3600)
            self.vault.put(platform, token)
        return token["access_token"]

    def disconnect(self, platform):
        token = self.vault.get(platform)
        if token:
            if platform == "tiktok":
                response = self.client.post("https://open.tiktokapis.com/v2/oauth/revoke/", data={
                    "client_key": settings.tiktok_client_key, "client_secret": settings.tiktok_client_secret,
                    "token": token["access_token"]})
            else:
                response = self.client.post("https://oauth2.googleapis.com/revoke", data={"token": token["access_token"]})
            if not response.is_success:
                raise PlatformError(platform, response.status_code, "revocation_failed")
        self.vault.delete(platform)
        with Session.begin() as db:
            row = db.scalar(select(PlatformConnection).where(PlatformConnection.platform == platform))
            if row:
                row.status = "AUTH_REQUIRED"


class Google:
    def __init__(self, platform="google", client=None, oauth=None):
        self.platform = platform
        self.client = client or httpx.Client(timeout=120)
        self.oauth = oauth or OAuth(client=self.client)

    def headers(self):
        return {"Authorization": "Bearer "+self.oauth.token(self.platform)}

    def request(self, method, url, **kwargs):
        response = self.client.request(method, url, headers={**self.headers(), **kwargs.pop("headers", {})}, **kwargs)
        if not response.is_success:
            code = "quota_or_permission" if response.status_code in {403,429} else "request_failed"
            raise PlatformError(self.platform, response.status_code, code)
        return response

    def folders(self):
        return self.request("GET", "https://www.googleapis.com/drive/v3/files", params={
            "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
            "fields": "files(id,name,webViewLink)", "pageSize": 100}).json()["files"]

    def folder(self, name, parent=None):
        # Names are application constants, never SQL or query fragments from model output.
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        query = f"name='{escaped}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent:
            if not all(c.isalnum() or c in "_-" for c in parent):
                raise ValueError("Invalid folder ID")
            query += f" and '{parent}' in parents"
        found = self.request("GET", "https://www.googleapis.com/drive/v3/files",
                             params={"q": query, "fields": "files(id,name)", "pageSize": 10}).json()["files"]
        if found:
            return found[0]["id"]
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent:
            body["parents"] = [parent]
        return self.request("POST", "https://www.googleapis.com/drive/v3/files", json=body).json()["id"]

    def drive_layout(self):
        with Session() as db:
            prefs = db.get(UserSettings, "preferences")
            chosen = prefs.values.get("drive_folder_id", "") if prefs else ""
        root = chosen or settings.google_drive_folder_id or self.folder("AI Content Factory")
        result = {"root": root}
        for channel, children in {"WonderNest Kids": ["Shorts", "Episodes", "Characters", "Backgrounds", "Published"],
                                  "How It Actually Works": ["Videos", "Assets", "Published"]}.items():
            parent = self.folder(channel, root)
            for name in children:
                result[channel+"/"+name] = self.folder(name, parent)
        return result

    def upload(self, path, body, key, *, youtube=False):
        """Persist resumable URLs in the protected vault, resume acknowledged byte ranges.

        If initiation has an ambiguous network failure, do not retry automatically.
        """
        if not youtube and body.get("appProperties", {}).get("factoryKey"):
            escaped = key.replace("\\", "\\\\").replace("'", "\\'")
            found = self.request("GET", "https://www.googleapis.com/drive/v3/files", params={
                "q": "appProperties has { key='factoryKey' and value='"+escaped+"' } and trashed=false",
                "fields": "files(id,webViewLink)", "pageSize": 1}).json().get("files", [])
            if found:
                return found[0]
        token = self.oauth.vault.get(self.platform)
        sessions = token.get("upload_sessions", {})
        session = sessions.get(key)
        total = path.stat().st_size
        if not session:
            if youtube:
                url = "https://www.googleapis.com/upload/youtube/v3/videos"
                params = {"uploadType": "resumable", "part": "snippet,status"}
            else:
                url = "https://www.googleapis.com/upload/drive/v3/files"
                params = {"uploadType": "resumable", "fields": "id,webViewLink"}
            response = self.request("POST", url, params=params, json=body, headers={
                "X-Upload-Content-Type": "video/mp4" if youtube else "application/octet-stream",
                "X-Upload-Content-Length": str(total)})
            session = response.headers.get("location")
            if not session or urlparse(session).hostname not in {"www.googleapis.com", "youtube.googleapis.com"}:
                raise PlatformError(self.platform, code="invalid_upload_location")
            token["upload_sessions"] = {**sessions, key: session}
            self.oauth.vault.put(self.platform, token)
            offset = 0
        else:
            response = self.client.put(session, headers={**self.headers(), "Content-Range": f"bytes */{total}",
                                                         "Content-Length": "0"})
            if response.is_success:
                return response.json()
            if response.status_code != 308:
                raise PlatformError(self.platform, response.status_code, "upload_session_expired_reconcile_before_retry")
            offset = int(response.headers.get("range", "bytes=0--1").split("-")[-1])+1 if response.headers.get("range") else 0
        with path.open("rb") as stream:
            stream.seek(offset)
            while offset < total:
                chunk = stream.read(8*1024*1024)
                response = self.client.put(session, headers={**self.headers(),
                    "Content-Type": "video/mp4" if youtube else "application/octet-stream",
                    "Content-Range": f"bytes {offset}-{offset+len(chunk)-1}/{total}"}, content=chunk)
                if response.status_code == 308:
                    acknowledged = response.headers.get("range")
                    offset = int(acknowledged.split("-")[-1])+1 if acknowledged else 0
                    stream.seek(offset)
                elif response.is_success:
                    return response.json()
                else:
                    raise PlatformError(self.platform, response.status_code, "resumable_upload_failed")
        raise PlatformError(self.platform, code="missing_upload_confirmation")

    def identity(self):
        if self.platform == "youtube":
            return self.request("GET", "https://www.googleapis.com/youtube/v3/channels",
                                params={"part": "id,snippet,statistics", "mine": "true"}).json()
        return self.request("GET", "https://www.googleapis.com/drive/v3/about",
                            params={"fields": "user(displayName,emailAddress),storageQuota"}).json()

    def video_status(self, video_id):
        return self.request("GET", "https://www.googleapis.com/youtube/v3/videos",
                            params={"part": "status,statistics", "id": video_id}).json()


class TikTok:
    BASE = "https://open.tiktokapis.com/v2"

    def __init__(self, client=None, oauth=None):
        self.client = client or httpx.Client(timeout=120)
        self.oauth = oauth or OAuth(client=self.client)

    def request(self, method, path, **kwargs):
        response = self.client.request(method, self.BASE+path,
                                       headers={"Authorization": "Bearer "+self.oauth.token("tiktok")}, **kwargs)
        if not response.is_success:
            raise PlatformError("tiktok", response.status_code)
        data = response.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            raise PlatformError("tiktok", response.status_code, data["error"]["code"])
        return data.get("data", {})

    def identity(self):
        return self.request("GET", "/user/info/", params={"fields": "open_id,display_name,avatar_url"})

    def creator_info(self):
        return self.request("POST", "/post/publish/creator_info/query/", json={})

    def init_inbox(self, path):
        # Upload-to-inbox requires the user to finish posting in TikTok. It is never called "published".
        total = path.stat().st_size
        chunk = min(total, 10*1024*1024)
        count = max(1, total//chunk)
        return self.request("POST", "/post/publish/inbox/video/init/", json={"source_info": {
            "source": "FILE_UPLOAD", "video_size": total, "chunk_size": chunk, "total_chunk_count": count}})

    def transfer(self, path, upload_url):
        host = urlparse(upload_url).hostname or ""
        if urlparse(upload_url).scheme != "https" or not (host.endswith(".tiktokapis.com") or host.endswith(".tiktok.com")):
            raise ValueError("Untrusted TikTok upload URL")
        total = path.stat().st_size
        nominal = min(total, 10*1024*1024)
        with path.open("rb") as stream:
            offset = 0
            while offset < total:
                remaining = total-offset
                size = remaining if remaining < 2*nominal else nominal
                content = stream.read(size)
                response = self.client.put(upload_url, headers={"Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{offset+len(content)-1}/{total}"}, content=content)
                if response.status_code not in {201,206}:
                    raise PlatformError("tiktok", response.status_code, "transfer_failed")
                offset += len(content)

    def status(self, publish_id):
        return self.request("POST", "/post/publish/status/fetch/", json={"publish_id": publish_id})


    def init_direct(self, path, post_info):
        total = path.stat().st_size
        chunk = min(total, 10*1024*1024)
        return self.request("POST", "/post/publish/video/init/", json={"post_info": post_info,
            "source_info": {"source": "FILE_UPLOAD", "video_size": total, "chunk_size": chunk,
                            "total_chunk_count": max(1, total//chunk)}})
