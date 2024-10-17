import json

import aiohttp
from tenacity import retry, stop_after_attempt, wait_random

from utils import logger
from utils.session import BaseClient


class LoginException(Exception):
    pass


class GrassRest(BaseClient):
    def __init__(self, email: str, password: str, proxy: str = None):
        super().__init__(proxy)
        self.email = email
        self.password = password

        self.session = aiohttp.ClientSession()

    async def enter_account(self):
        res_json = await self.handle_login()

        self.website_headers['Authorization'] = res_json['result']['data']['accessToken']

        return res_json['result']['data']['userId']

    @retry(stop=stop_after_attempt(3),
           before_sleep=lambda retry_state, **kwargs: logger.info(f"Retrying... {retry_state.outcome.exception()}"),
           reraise=True)
    async def retrieve_user(self):
        url = 'https://api.getgrass.io/retrieveUser'
        response = await self.session.get(url, headers=self.website_headers, proxy=self.proxy)

        return await response.json()

    async def handle_login(self):
        handler = retry(
            stop=stop_after_attempt(4),
            before_sleep=lambda retry_state, **kwargs: logger.info(f"{self.email} | Login retrying... "
                                                                   f"{retry_state.outcome.exception()}"),
            wait=wait_random(8, 12),
            reraise=True
        )

        return await handler(self.login)()

    async def login(self):
        url = 'https://api.getgrass.io/login'

        json_data = {
            'password': self.password,
            'username': self.email,
        }

        response = await self.session.post(url, headers=self.website_headers, json=json_data,
                                           proxy=self.proxy)
        logger.debug(f"{self.email} | Login response: {await response.text()}")

        res_json = await response.json()
        if res_json.get("error") is not None:
            raise LoginException(f"Login stopped: {res_json['error']['message']}")

        if response.status != 200:
            raise aiohttp.ClientConnectionError(f"Login response: | {await response.text()}")

        return res_json

    @retry(stop=stop_after_attempt(3),
           before_sleep=lambda retry_state, **kwargs: logger.info(f"Retrying... {retry_state.outcome.exception()}"),
           reraise=True)
    async def retrieve_user(self):
        url = "https://api.getgrass.io/retrieveUser"

        response = await self.session.get(url, headers=self.website_headers, proxy=self.proxy)
        logger.debug(f"{self.email} | Change email response: {await response.text()}")
        result = await response.json()

        if result.get("error") is not None:
            raise aiohttp.ClientConnectionError(f"Change email response: {await response.text()}")

        return result

    async def close(self):
        await self.session.close()
