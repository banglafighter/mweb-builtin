from enum import Enum


class MWebHttpConst:
    APPLICATION_JSON = "application/json"
    SUCCESS = "success"
    ERROR = "error"
    UTF8_ENCODING = "utf-8"


class MWebHttpRequestType(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
