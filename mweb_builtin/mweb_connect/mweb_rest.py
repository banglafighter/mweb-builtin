from mw_common import Console, SDLize, MwException
from .mweb_rest_data import MWebRestCredentials, MWebRestLoginToken, MWebRestResponse, MWebRestLoginResponse, \
    MWebRestRequestData
from ..mhttp import MWebHttpConst
from ..mhttp.mweb_http import MWebHttp, MWebHttpResponse
from ..mhttp.mweb_http_const import MWebHttpRequestType


class MWebRest:
    _mweb_http: MWebHttp = None
    _credentials: MWebRestCredentials = None
    _rest_token: MWebRestLoginToken = None
    _enable_log: bool = False

    def __init__(self, credentials: MWebRestCredentials, enable_log: bool = False):
        self._mweb_http = MWebHttp(base_url=credentials.baseUrl)
        self._enable_log = enable_log
        self._credentials = credentials

    def log(self, content):
        if self._enable_log:
            Console.log(content)

    def _prepare_json_request_data(self, request_obj: SDLize, json_dict: dict = None):
        if request_obj:
            json_dict = request_obj.to_dict()
        elif json_dict:
            return {"data": json_dict}
        return json_dict

    def _get_data(self, response: MWebHttpResponse, response_obj: SDLize, exception=True, is_data_response=True):
        response_data = response.data
        self.log(response_data)
        if response.status != MWebHttpConst.SUCCESS or not response_data:
            if exception:
                raise MwException("Unable to process request").add_data(response_data)
            return None
        response = MWebRestResponse().load_dict(response_data)
        if response_obj and response.data:
            response.data = response_obj.load_dict(response.data)
        if is_data_response:
            return response.data
        return response

    def _set_token(self, token: MWebRestLoginToken):
        if not token or not token.accessToken or not token.refreshToken:
            raise MwException("Unable to set token")
        self._rest_token = token

    async def _init_auth(self):
        request_data = {
            self._credentials.usernameFieldName: self._credentials.username,
            self._credentials.passwordFieldName: self._credentials.password,
        }
        raw_response = await self._mweb_http.post(url=self._credentials.loginUrl, json_dict={"data": request_data})
        response = self._get_data(response=raw_response, response_obj=MWebRestLoginResponse())
        if not response:
            raise MwException(message="Invalid response from remote")
        self._set_token(token=response.token)
        await self.after_authenticate_success(raw_response=raw_response)

    async def after_authenticate_success(self, raw_response):
        pass

    async def _renew_token(self, base_url: str = None):
        try:
            if not self._rest_token.refreshToken:
                raise MwException(message="Credentials Expired")
            request_data = {
                "refreshToken": self._rest_token.refreshToken,
            }

            if base_url:
                self._mweb_http.set_base(url=base_url)

            raw_response = await self._mweb_http.post(
                url=self._credentials.renewTokenUrl,
                json_dict={"data": request_data}
            )
            response = self._get_data(response=raw_response, response_obj=MWebRestLoginToken())
            self._set_token(token=response)
        except:
            Console.log(message="Unable to renew token", system_log=True)
            await self._init_auth()

    async def _init_config(self, is_open_auth: bool = False, base_url: str = None):
        if not self._credentials:
            raise MwException(message="Please provide credentials.")

        if not base_url:
            base_url = self._credentials.baseUrl
        self._mweb_http.set_base(url=base_url)

        if is_open_auth:
            return

        if not self._rest_token or not self._rest_token.accessToken:
            await self._init_auth()
        self._mweb_http.add_bearer_token(self._rest_token.accessToken)

    async def _send_request(self, request_data: MWebRestRequestData) -> MWebHttpResponse:
        response = None
        if request_data.requestType == MWebHttpRequestType.POST:
            response = await self._mweb_http.post(url=request_data.url, json_dict=request_data.jsonDict, data=request_data.data, file=request_data.file, verify=request_data.sslVerify)
        elif request_data.requestType == MWebHttpRequestType.PUT:
            response = await self._mweb_http.put(url=request_data.url, json_dict=request_data.jsonDict, data=request_data.data, file=request_data.file, verify=request_data.sslVerify)
        elif request_data.requestType == MWebHttpRequestType.PATCH:
            response = await self._mweb_http.patch(url=request_data.url, json_dict=request_data.jsonDict, data=request_data.data, file=request_data.file, verify=request_data.sslVerify)
        elif request_data.requestType == MWebHttpRequestType.DELETE:
            response = await self._mweb_http.delete(url=request_data.url, params=request_data.params, verify=request_data.sslVerify)
        else:
            response = await self._mweb_http.get(url=request_data.url, params=request_data.params)
        request_summary = f"URL: {self._mweb_http.baseUrl} \nURL Postfix: {request_data.url} \nparams: {request_data.params} \nJSON Data: {request_data.jsonDict}"
        self.log(request_summary)
        return response


    async def process_rest_request(self, request_data: MWebRestRequestData, response_obj: SDLize = None):
        await self._init_config(is_open_auth=request_data.isOpenAuth)
        response: MWebHttpResponse = await self._send_request(request_data=request_data)
        if response.httpCode == 401:
            await self._renew_token()
            response: MWebHttpResponse = await self._send_request(request_data=request_data)
        return self._get_data(response=response, response_obj=response_obj, exception=request_data.exception, is_data_response=request_data.isDataResponse)

    async def get_request(self, url: str, params: dict = None, response_obj: SDLize = None, exception: bool = True, is_open_auth: bool = False, is_data_response: bool = True, ssl_verify: bool = True):
        return await self.process_rest_request(request_data=MWebRestRequestData(url=url, params=params, requestType=MWebHttpRequestType.GET, exception=exception, isOpenAuth=is_open_auth, isDataResponse=is_data_response, sslVerify=ssl_verify), response_obj=response_obj)

    async def delete_request(self, url: str, params: dict = None, response_obj: SDLize = None, exception: bool = True, is_open_auth: bool = False, is_data_response=True, ssl_verify: bool = True):
        return await self.process_rest_request(request_data=MWebRestRequestData(url=url, params=params, requestType=MWebHttpRequestType.DELETE, exception=exception, isOpenAuth=is_open_auth, isDataResponse=is_data_response, sslVerify=ssl_verify), response_obj=response_obj)

    async def post_request(self, url: str, request_obj: SDLize = None, json_dict: dict = None, data: dict = None, file: dict = None, response_obj: SDLize = None, exception: bool = True, is_open_auth: bool = False, is_data_response=True, ssl_verify: bool = True):
        json_dict = self._prepare_json_request_data(request_obj=request_obj, json_dict=json_dict)
        return await self.process_rest_request(request_data=MWebRestRequestData(url=url, jsonDict=json_dict, data=data, file=file, requestType=MWebHttpRequestType.POST, exception=exception, isOpenAuth=is_open_auth, isDataResponse=is_data_response, sslVerify=ssl_verify), response_obj=response_obj)

    async def put_request(self, url: str, request_obj: SDLize = None, json_dict: dict = None, data: dict = None, file: dict = None, response_obj: SDLize = None, exception: bool = True, is_open_auth: bool = False, is_data_response=True, ssl_verify: bool = True):
        json_dict = self._prepare_json_request_data(request_obj=request_obj, json_dict=json_dict)
        return await self.process_rest_request(request_data=MWebRestRequestData(url=url, jsonDict=json_dict, data=data, file=file, requestType=MWebHttpRequestType.PUT, exception=exception, isOpenAuth=is_open_auth, isDataResponse=is_data_response, sslVerify=ssl_verify), response_obj=response_obj)

    async def patch_request(self, url: str, request_obj: SDLize = None, json_dict: dict = None, data: dict = None, file: dict = None, response_obj: SDLize = None, exception: bool = True, is_open_auth: bool = False, is_data_response=True, ssl_verify: bool = True):
        json_dict = self._prepare_json_request_data(request_obj=request_obj, json_dict=json_dict)
        return await self.process_rest_request(request_data=MWebRestRequestData(url=url, jsonDict=json_dict, data=data, file=file, requestType=MWebHttpRequestType.PATCH, exception=exception, isOpenAuth=is_open_auth, isDataResponse=is_data_response, sslVerify=ssl_verify), response_obj=response_obj)

    async def close(self):
        await self._mweb_http.close()
