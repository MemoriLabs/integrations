"""HTTP against Memori, plus how failures are reported."""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from memori import config

# Recall runs in front of every prompt, so the budget is how long a user will
# wait before typing.
TIMEOUT = 10.0

# Capture holds the turn open, so hooks.json bounds it
CAPTURE_TIMEOUT = 4.0

# Compaction runs an LLM over the session's memories in rolling batches. It
# fires once, after a compaction, so it can afford to wait.
COMPACTION_TIMEOUT = 35.0


class SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """
    Refuse a redirect that would carry the credentials to another host.

    urllib copies every header onto the redirected request, with no same-origin
    check: a 302 to a different host arrives holding the
    identity token and the client key. `requests` strips them here; urllib does
    not. A redirect within the same host is left alone, since that is ordinary
    path or scheme normalisation and the credentials are not going anywhere new.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        was = urllib.parse.urlparse(req.full_url)
        now = urllib.parse.urlparse(newurl)

        # Off the host, or off TLS. An upgrade to https is fine; the reverse
        # would put the credentials on the wire in the clear.
        if now.netloc != was.netloc:
            refused = "to another host"
        elif was.scheme == "https" and now.scheme != "https":
            refused = "from https to plain http"
        else:
            return super().redirect_request(req, fp, code, msg, headers, newurl)

        raise urllib.error.HTTPError(
            newurl,
            code,
            f"refused a redirect {refused}, which would have sent the identity "
            "token and client key there. Check the api url.",
            headers,
            fp,
        )


# Replaces urllib's default redirect handler, being a subclass of it.
OPENER = urllib.request.build_opener(SameHostRedirects)


def request(path, body=None, timeout=TIMEOUT):
    """
    The primitive. A body means POST, no body means GET.

    `get` and `post` below are the sugar for the two call sites that know their
    shape; the diagnostic calls this directly, because it walks a table of
    endpoints where the body, and so the method, differs per row.
    """

    headers = {
        "Authorization": f"Bearer {config.setting('identity_token')}",
        "Content-Type": "application/json",
        config.setting("api_header_name"): config.setting("api_header_value"),
    }

    call = urllib.request.Request(
        f"{config.setting('api_url').rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method="GET" if body is None else "POST",
    )

    with OPENER.open(call, timeout=timeout) as response:
        raw = response.read()

    return json.loads(raw) if raw else {}


def get(path, timeout=TIMEOUT):
    return request(path, timeout=timeout)


def post(path, body, timeout=TIMEOUT):
    return request(path, body=body, timeout=timeout)


def attribution():
    return {"entity": {"id": config.setting("entity_id")}}


def log(message):
    if config.debug():
        sys.stderr.write(f"[memori] {message}\n")


def warn(message):
    """For problems that will never fix themselves, so they are not silent."""

    sys.stderr.write(f"[memori] {message}\n")


def report_failure(what, error):
    """Log every failure, and warn on the ones a user has to act on."""

    log(f"{what} failed: {error}")

    if isinstance(error, urllib.error.HTTPError) and error.code == 401:
        warn(
            f"{what} was rejected as unauthorized. Check the identity token and "
            "client API key. Run the Memori check for details."
        )
