from dataclasses import dataclass
from mw_common import SDLize
from ..mhttp import MWebHttpConst
from ..mhttp.mweb_http_const import MWebHttpRequestType


@dataclass
class MWebRestCredentials(SDLize):
    baseUrl: str
    username: str = None
    password: str = None
    usernameFieldName: str = "username"
    passwordFieldName: str = "password"
    loginUrl: str = None
    renewTokenUrl: str = None


@dataclass
class MWebRestLoginToken(SDLize):
    accessToken: str = None
    refreshToken: str = None


@dataclass
class MWebRestLoginResponse(SDLize):
    token: MWebRestLoginToken = None


@dataclass
class MWebRestPaginationResponse(SDLize):
    page: int = None
    itemPerPage: int = None
    total: int = None
    totalPage: int = None


@dataclass
class MWebRestResponse(SDLize):
    status: str = None
    code: str = None
    message: str = None
    data: object = None
    pagination: MWebRestPaginationResponse = None

    def get_data(self):
        if self.status == MWebHttpConst.SUCCESS:
            return self.data
        return None

    def is_success(self):
        return self.status == MWebHttpConst.SUCCESS


@dataclass
class MWebRestRequestData(SDLize):
    url: str
    requestType: MWebHttpRequestType
    jsonDict: dict = None
    data: dict = None
    params: dict = None
    file: dict = None
    exception: bool = True
    isOpenAuth: bool = False
    isDataResponse: bool = True
    sslVerify: bool = True
