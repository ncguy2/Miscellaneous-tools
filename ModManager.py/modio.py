import requests


class ModioClient(object):
    """
    A REST client for http://mod.io, hiding the ugly http requests behind a nice interface :)
    """

    HEADERS = {
        'Accept': 'application/json'
    }

    BASE_URL = "https://api.mod.io/v1"

    def __init__(self, api_key):
        self.api_key = api_key

    def get_games(self, filter: str = None):
        return self._request("/games", filter=filter, ret_type=Game, decompose=True)

    def get_mods(self, game_id: int, filter: str = None):
        return self._request(f"/games/{game_id}/mods", filter=filter, ret_type=Mod, decompose=True)

    def get_files(self, game_id: int, mod_id: int, filter: str = None):
        return self._request(f"/games/{game_id}/mods/{mod_id}/files", filter=filter, ret_type=self._create_file_array)

    def get_game(self, game_id: int):
        return self._request(f"/games/{game_id}", ret_type=Game)

    def get_mod(self, game_id: int, mod_id: int):
        return self._request(f"/games/{game_id}/mods/{mod_id}", ret_type=Mod)

    def get_file(self, game_id: int, mod_id: int, file_id: int):
        return self._request(f"/games/{game_id}/mods/{mod_id}/files/{file_id}", ret_type=File)

    def _create_file_array(self, _, file_data):
        data = file_data['data']
        arr = []
        for v in data:
            arr.append(File(self, v))
        return arr

    def _request(self, path, params=None, filter: str = None, ret_type=None, decompose: bool = False):
        if params is None:
            params = {}
        params['api_key'] = self.api_key
        url = self.BASE_URL + path
        if filter:
            s = filter.split("=")
            params[s[0]] = s[1]

        # Client.__debug_url(url, params)

        r = requests.get(url, params=params, headers=self.HEADERS)
        data = r.json()

        if ret_type:
            if decompose:
                return [ret_type(self, v) for k, v in data.items()]
            return ret_type(self, data)
        return data

    @staticmethod
    def __debug_url(url, params):
        param_strs = []
        for k, v in params.items():
            param_strs.append(f"{k}={v}")
        param_str = "?" + "&".join(param_strs)
        dbg_url = url + param_str
        print(f"[DEBUG] Request to {dbg_url}")


class ModioObject(object):
    def __init__(self, client: ModioClient):
        self.client = client

    @property
    def id(self):
        return self['id']

    @property
    def name(self):
        return self['name']

    def __getitem__(self, item):
        return self.data[item]

    def __len__(self):
        return len(self.data)


class Game(ModioObject):
    def __init__(self, client: ModioClient, data):
        super().__init__(client)
        self.data = data

    def get_mods(self):
        return self.client.get_mods(self.id)

    def get_mod(self, mod_id: int):
        return self.client.get_mod(self.id, mod_id)


class Mod(ModioObject):
    def __init__(self, client: ModioClient, data):
        super().__init__(client)
        self.data = data

    @property
    def game_id(self):
        return self['game_id']

    def get_files(self):
        return self.client.get_files(self.game_id, self.id)

    def get_file(self, file_id: int):
        return self.client.get_file(self.game_id, self.id, file_id)

    def get_latest_file(self):
        files = self.get_files()
        files.sort(key=lambda x: -x.timestamp)
        return files[0]


class File(ModioObject):
    def __init__(self, client: ModioClient, data):
        super().__init__(client)
        self.data = data

    @property
    def name(self):
        return self['filename']

    @property
    def mod_id(self):
        return self['mod_id']

    @property
    def timestamp(self):
        return self['date_added']

    @property
    def download_url(self):
        return self['download']['binary_url']
