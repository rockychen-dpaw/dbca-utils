import requests
import os
import six

session_key_header = "X_SESSION_KEY"
http_session_key_header = "HTTP_{}".format(session_key_header)
sso_cookie_name = os.environ.get(
    "SSO_COOKIE_NAME") or "_dpaw_wa_gov_au_sessionid"
debug = (os.environ.get("DEBUG_SSO") or "false").lower() in [
    "true", "yes", "t", "y", "on"]

if debug:
    import json as json_lib
    request_seq = 0


def _set_session_key(user_request, kwargs):
    """
    Get the session key from user request for sso
    if not found, return None
    """
    if not user_request:
        return

    session_key = None
    request_name = user_request.__module__ + "." + user_request.__class__.__name__
    try:
        if request_name[0:7] == "bottle.":
            session_key = user_request.get_header(
                session_key_header, user_request.get_header(
                    http_session_key_header, None))
        elif request_name[0:7] == "django.":
            session_key = user_request.META.get(
                http_session_key_header, user_request.META.get(
                    session_key_header, None))
        else:
            session_key = user_request.META.get(
                http_session_key_header, user_request.META.get(
                    session_key_header, None))
    except:
        pass

    if not session_key:
        # Try to use the current session id
        try:
            session_key = user_request.session.session_key
        except:
            pass
    if session_key:
        cookies = kwargs.get("cookies", {})
        cookies[sso_cookie_name] = session_key
        kwargs["cookies"] = cookies

    return


log_head_format = """{}-{}: {}
    server-side request: {}  {}
        header:
             {}
"""


def log(user_request, url, method, data=None, json=None, kwargs=None):
    global request_seq
    request_seq += 1
    try:
        request_path = user_request.path
    except:
        request_path = ""
    log_msg = log_head_format.format(os.getpid(), request_seq, request_path,
                                     url, method,
                                     ("\n" + ' ' * 12).join(["{}={}".format(k, v) for k, v in (kwargs or {}).iteritems()]))
    if data:
        log_msg += "{}body(data): {}\n".format(' ' * 8, str(data))

    if json:
        json_out = six.StringIO()
        try:
            json_lib.dump(json, json_out, indent=4)
            json_str = "\n".join(
                [" " * 12 + line for line in json_out.getvalue().split("\n")])
        finally:
            json_out.close()

        log_msg += "{}body(json):\n{}\n".format(' ' * 8, json_str)

    print(log_msg)


def options(user_request, url, **kwargs):
    """ A wrapper of requests.options.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a OPTIONS request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """
    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "OPTIONS", kwargs=kwargs)

    return requests.options(url, **kwargs)


def head(user_request, url, **kwargs):
    """ A wrapper of requests.head.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a HEAD request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "HEAD", kwargs=kwargs)

    return requests.head(url, **kwargs)


def get(user_request, url, **kwargs):
    """ A wrapper of requests.get.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a GET request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "GET", kwargs=kwargs)

    return requests.get(url, **kwargs)


def post(user_request, url, data=None, json=None, **kwargs):
    """ A wrapper of requests.post.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a POST request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in the body of the :class:`Request`.
    :param json: (optional) json data to send in the body of the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "POST", data=data, json=json, kwargs=kwargs)

    return requests.post(url, data, json, **kwargs)


def put(user_request, url, data=None, **kwargs):
    """ A wrapper of requests.put.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a PUT request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in the body of the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "PUT", data=data, kwargs=kwargs)

    return requests.put(url, data, **kwargs)


def patch(user_request, url, data=None, **kwargs):
    """ A wrapper of requests.patch.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a PATCH request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param data: (optional) Dictionary, bytes, or file-like object to send in the body of the :class:`Request`.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "PATCH", data=data, kwargs=kwargs)

    return requests.patch(url, data, **kwargs)


def delete(user_request, url, **kwargs):
    """ A wrapper of requests.delete.
    This method will automatically add user's session key as the cookie to enable sso

    Sends a DELETE request. Returns :class:`Response` object.

    :param user_request: The http request contains the authentication key and is triggered by user.
    :param url: URL for the new :class:`Request` object.
    :param \*\*kwargs: Optional arguments that ``request`` takes.
    """

    _set_session_key(user_request, kwargs)

    if debug:
        log(user_request, url, "DELETE", kwargs=kwargs)

    return requests.delete(url, **kwargs)
