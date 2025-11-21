from dataclasses import dataclass
import aiohttp
from aiohttp import ClientSession
from mw_common import SDLize, MwException
from .mweb_http_const import MWebHttpConst


@dataclass(kw_only=True)
class MWebHttpResponse(SDLize):
    status: str = None
    httpCode: int = None
    data: dict | list | str | None = None
    contentType: str = None

    async def process_response(self, response) -> "MWebHttpResponse":
        self.httpCode = response.status
        if 200 <= self.httpCode < 300:
            self.status = MWebHttpConst.SUCCESS
        else:
            self.status = MWebHttpConst.ERROR

        await self.set_data(response)
        return self

    async def set_data(self, response):
        self.contentType = response.headers.get("Content-Type")
        if self.contentType and self.contentType.lower().startswith(MWebHttpConst.APPLICATION_JSON):
            self.data = await response.json()
        else:
            self.data = await response.text()

    @classmethod
    async def get_response(cls, response) -> "MWebHttpResponse":
        http_response = MWebHttpResponse()
        await http_response.process_response(response)
        return http_response


class MWebHttp:
    headers: dict = {}
    baseUrl: str = None
    session: ClientSession = None

    def __init__(self, base_url: str = None):
        self.headers = {}
        self.baseUrl = base_url
        self.session = aiohttp.ClientSession()

    def _get_url(self, url):
        if not self.baseUrl or self.baseUrl == "":
            raise MwException("HTTP Base url is empty")
        return self.baseUrl + url

    def set_base(self, url) -> "MWebHttp":
        self.baseUrl = url
        return self

    async def get(self, url: str, params: dict = None, verify: bool = True) -> MWebHttpResponse:
        url = self._get_url(url)
        async with self.session.get(url, headers=self.headers, params=params, ssl=verify) as response:
            return await MWebHttpResponse.get_response(response=response)

    async def post(self, url: str, json_dict: dict = None, data: dict = None, file: dict = None, verify: bool = True) -> MWebHttpResponse:
        url = self._get_url(url)
        async with self.session.post(
                url,
                headers=self.headers,
                json=json_dict,
                data=data,
                files=file,
                ssl=verify
        ) as response:
            return await MWebHttpResponse.get_response(response=response)

    async def put(self, url: str, json_dict: dict = None, data: dict = None, file: dict = None, verify: bool = True) -> MWebHttpResponse:
        url = self._get_url(url)
        async with self.session.put(
                url,
                headers=self.headers,
                json=json_dict,
                data=data,
                files=file,
                ssl=verify
        ) as response:
            return await MWebHttpResponse.get_response(response=response)

    async def patch(self, url: str, json_dict: dict = None, data: dict = None, file: dict = None, verify: bool = True) -> MWebHttpResponse:
        url = self._get_url(url)
        async with self.session.patch(
                url,
                headers=self.headers,
                json=json_dict,
                data=data,
                files=file,
                ssl=verify
        ) as response:
            return await MWebHttpResponse.get_response(response=response)

    async def delete(self, url: str, params: dict = None, verify: bool = True) -> MWebHttpResponse:
        url = self._get_url(url)
        async with self.session.delete(url, headers=self.headers, params=params, ssl=verify) as response:
            return await MWebHttpResponse.get_response(response=response)

    def add_header(self, key: str, value) -> "MWebHttp":
        self.headers[key] = value
        return self

    def add_bearer_token(self, token) -> "MWebHttp":
        self.add_header("Authorization", f"Bearer {token}")
        return self

    def add_content_type(self, content_type) -> "MWebHttp":
        self.add_header("Content-Type", str(content_type))
        return self

    async def close(self):
        await self.session.close()
