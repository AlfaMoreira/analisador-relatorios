"""OAuth público com PKCE; credenciais somente no cofre do Windows."""
import base64
import hashlib
import secrets
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import requests
from . import vault

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


class AuthError(RuntimeError):
    pass


def request_json(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        if not response.ok:
            raise AuthError(f"OpenAI retornou HTTP {response.status_code}. Tente entrar novamente ou confira sua conexão e permissões.")
        return response.json()
    except requests.RequestException:
        raise AuthError("Não foi possível conectar à OpenAI. Confira sua conexão.") from None


def validate_callback(path, state, client_id=None):
    parsed = urlsplit(path)
    values = parse_qs(parsed.query)
    if parsed.path != "/auth/callback" or any(len(v) != 1 for v in values.values()):
        raise AuthError("Retorno de autenticação inválido.")
    if not secrets.compare_digest(values.get("state", [""])[0], state):
        raise AuthError("O retorno não corresponde à tentativa de login.")
    if "error" in values:
        raise AuthError("Login cancelado ou autorização recusada.")
    issued = values.get("client_id", [client_id])[0]
    if not issued or issued == "dynamic_agent_client" or (client_id and issued != client_id):
        raise AuthError("Registro de cliente ausente ou incompatível.")
    code = values.get("code", [""])[0]
    if not code:
        raise AuthError("Código de autenticação ausente.")
    return code, issued


class Auth:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._discovery = None
        path = self.data_dir / "host-id.txt"
        if not path.exists():
            path.write_text("urn:uuid:" + str(uuid.uuid4()), encoding="utf-8")
        self.host_id = path.read_text(encoding="utf-8").strip()

    def load(self):
        path = self.data_dir / "credentials.dpapi"
        return vault.read(path) if path.exists() else {"accounts": {}, "active": None}

    def save(self, data):
        # Falha fechada: não existe fallback que grave tokens em texto aberto.
        vault.write(self.data_dir / "credentials.dpapi", data)

    def discovery(self):
        if self._discovery is None:
            doc = request_json("GET", ISSUER + "/.well-known/openid-configuration")
            if doc.get("issuer") != ISSUER:
                raise AuthError("Emissor OpenID inesperado.")
            for field in ("authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint"):
                url = urlsplit(doc.get(field, ""))
                if url.scheme != "https" or url.hostname != "auth.openai.com":
                    raise AuthError("Endpoint OpenID não confiável.")
            self._discovery = doc
        return self._discovery

    def accounts(self):
        data = self.load()
        return [(cid, a.get("email") or a.get("subject") or "Registro pendente", cid == data["active"])
                for cid, a in data["accounts"].items()]

    def select(self, cid):
        data = self.load()
        if cid not in data["accounts"]:
            raise AuthError("Conta não encontrada.")
        data["active"] = cid
        self.save(data)

    def sign_in(self, selected=None, cancel=None):
        with self.lock:
            doc = self.discovery()
            data = self.load()
            previous = data["accounts"].get(selected, {})
            state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
            result = {}

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass  # O código e os hints nunca entram em logs.

                def do_GET(self):
                    if urlsplit(self.path).path != "/auth/callback":
                        self.send_error(404)
                        return
                    try:
                        result["value"] = validate_callback(self.path, state, selected)
                        message = "Retorno recebido. Volte ao Analisador de Relatórios para conferir o login."
                        status = 200
                    except AuthError as exc:
                        # Retornos sem state correto não encerram o listener legítimo.
                        incoming = parse_qs(urlsplit(self.path).query).get("state", [""])[0]
                        if secrets.compare_digest(incoming, state):
                            result["error"] = exc
                        message, status = "Retorno de login inválido ou recusado.", 400
                    self.send_response(status)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(message.encode())

            with HTTPServer(("127.0.0.1", 0), Handler) as server:
                server.timeout = 0.5
                redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
                params = dict(client_id=selected or "dynamic_agent_client", ext_agent_host_id=self.host_id,
                              response_type="code", redirect_uri=redirect, scope=SCOPES, resource=RESOURCE,
                              state=state, nonce=nonce, code_challenge=challenge, code_challenge_method="S256")
                if selected:
                    if previous.get("id_token"):
                        params["id_token_hint"] = previous["id_token"]
                    if previous.get("email"):
                        params["login_hint"] = previous["email"]
                else:
                    params["agent_name_hint"] = "Analisador de Relatórios Celacanto"
                if not webbrowser.open(doc["authorization_endpoint"] + "?" + urlencode(params)):
                    raise AuthError("Não foi possível abrir o navegador padrão.")
                deadline = time.monotonic() + 180
                while not result and time.monotonic() < deadline:
                    if cancel and cancel.is_set():
                        raise AuthError("Login cancelado.")
                    server.handle_request()
            if "error" in result:
                raise result["error"]
            if "value" not in result:
                raise AuthError("O login expirou após 3 minutos. Tente novamente.")
            code, issued = result["value"]
            # Preserva o registro emitido mesmo se o código expirar na troca.
            data["accounts"].setdefault(issued, {"client_id": issued})
            self.save(data)
            tokens = request_json("POST", doc["token_endpoint"], data=dict(
                grant_type="authorization_code", client_id=issued, code=code,
                code_verifier=verifier, redirect_uri=redirect, resource=RESOURCE))
            try:
                signing = jwt.PyJWKClient(doc["jwks_uri"], timeout=30).get_signing_key_from_jwt(tokens["id_token"])
                claims = jwt.decode(tokens["id_token"], signing.key, algorithms=["RS256"],
                                    audience=issued, issuer=ISSUER,
                                    options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]})
                if not secrets.compare_digest(claims["nonce"], nonce):
                    raise ValueError("nonce")
                if previous.get("subject") and previous["subject"] != claims["sub"]:
                    raise ValueError("subject")
                if not tokens.get("access_token") or tokens.get("token_type", "").lower() != "bearer":
                    raise ValueError("token")
            except Exception:
                raise AuthError("A identidade retornada não pôde ser validada. Entre novamente.") from None
            data["accounts"][issued] = dict(tokens, client_id=issued, subject=claims["sub"],
                                            email=claims.get("email", ""), issuer=ISSUER,
                                            scopes=tokens.get("scope", "").split(),
                                            expires_at=time.time() + int(tokens.get("expires_in", 0)))
            data["active"] = issued
            self.save(data)
            return "Login validado. " + ("Uso do plano autorizado." if "chatgpt.tokens.use.direct" in data["accounts"][issued]["scopes"]
                                        else "Uso do plano não autorizado; entre novamente e autorize a IA.")

    def access_token(self):
        with self.lock:
            data = self.load()
            account = data["accounts"].get(data["active"], {})
            if not account.get("access_token"):
                raise AuthError("Entre com sua conta ChatGPT primeiro.")
            if account.get("expires_at", 0) < time.time() + 60:
                if not account.get("refresh_token"):
                    raise AuthError("Sessão expirada. Entre novamente.")
                tokens = request_json("POST", self.discovery()["token_endpoint"], data=dict(
                    grant_type="refresh_token", client_id=account["client_id"],
                    refresh_token=account["refresh_token"], resource=RESOURCE))
                if not tokens.get("access_token"):
                    raise AuthError("Renovação inválida. Entre novamente.")
                account.update(tokens)
                if "scope" in tokens:
                    account["scopes"] = tokens["scope"].split()
                account["expires_at"] = time.time() + int(tokens.get("expires_in", 0))
                self.save(data)
            if not {"chatgpt.tokens.use.direct", "resource.invoke"}.issubset(account.get("scopes", [])):
                raise AuthError("A conta está conectada, mas o uso do plano não foi autorizado. Entre novamente.")
            return account["access_token"]

    def sign_out(self):
        with self.lock:
            data = self.load()
            cid = data["active"]
            account = data["accounts"].get(cid, {})
            confirmed = True
            if account.get("refresh_token"):
                confirmed = False
                try:
                    endpoint = self.discovery()["revocation_endpoint"]
                    for attempt in range(3):
                        try:
                            response = requests.post(endpoint, data=dict(token=account["refresh_token"],
                                token_type_hint="refresh_token", client_id=cid), timeout=15)
                            if response.status_code == 200:
                                confirmed = True
                                break
                            if response.status_code < 500:
                                break
                        except requests.RequestException:
                            pass
                        time.sleep(0.5 * (2 ** attempt))
                except AuthError:
                    pass
            if cid:
                data["accounts"][cid] = {k: v for k, v in account.items()
                                         if k in {"client_id", "subject", "email", "issuer"}}
            data["active"] = None
            self.save(data)
            return "Sessão encerrada." if confirmed else "Sessão local encerrada. Revogação remota não confirmada; desconecte o app nas configurações do ChatGPT."
