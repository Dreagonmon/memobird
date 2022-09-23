from aiohttp import ClientSession, ClientTimeout, ClientResponse, CookieJar, FormData
from http.cookies import SimpleCookie, Morsel
from urllib.parse import urljoin
from yarl import URL
from pathlib import Path
from html import escape
import asyncio
import json

MB_INTERFACE_URL = "http://w.memobird.cn/cn/ashx/DBInterface.ashx"
MB_IMAGE_UPLOAD_URL = "http://w.memobird.cn/cn/Plug-in/ueditor/net/controller.ashx"

def parse_cookie(rawline: str, cookie=SimpleCookie()):
    mdata = Morsel()
    for fields in rawline.split(";"):
        k, v = fields.split("=")
        k = k.strip().lower()
        v = v.strip()
        if mdata.isReservedKey(k):
            mdata[k] = v
        else:
            mdata.set(k, v, v)
    # 非标准hack
    dict.__setitem__(cookie, mdata.key, mdata)
    return cookie

def update_cookies(jar: CookieJar, resp: ClientResponse):
    cookie=jar.filter_cookies(resp.url)
    try:
        for cookie_str in resp.headers.getall("Set-Cookie"):
            cookie = parse_cookie(cookie_str, cookie)
        jar.update_cookies(cookie, resp.url)
    except KeyError: pass

def cookiejar_to_dict(jar: CookieJar) -> dict[str, list[dict[str, str]]]:
    dict_domain = {}
    for cookie in jar:
        domain = cookie.get("domain", "")
        cookie_list = dict_domain.setdefault(domain, [])
        mdict = dict(cookie)
        mdict[cookie.key] = cookie.value
        cookie_list.append(mdict)
    return dict_domain

def cookiejar_from_dict(dict_domain: dict[str, list[dict[str, str]]]):
    jar = CookieJar()
    for domain, cookie_list in dict_domain.items():
        url = URL.build(host=domain)
        cookie = SimpleCookie()
        for mdict in cookie_list:
            mdata = Morsel()
            for k, v in mdict.items():
                if mdata.isReservedKey(k):
                    mdata[k] = v
                else:
                    mdata.set(k, v, v)
            # 非标准hack
            dict.__setitem__(cookie, mdata.key, mdata)
        jar.update_cookies(cookie, url)
    return jar

class MemobirdClient:
    def __init__(self, save_path="memobird.json") -> None:
        self.save_path = save_path
        self.cookie_jar = None
        self.client = None
        self.user_id = ""
        self.user_name = ""
        self.devices = [] # (name, guid)
        self.qr_parameter = ""
    
    @property
    def is_logged_in(self):
        return isinstance(self.user_id, str) and len(self.user_id) > 8

    async def init(self):
        if self.cookie_jar == None:
            try:
                with open(self.save_path, "r") as f:
                    save_data = json.load(f)
                self.cookie_jar = cookiejar_from_dict(save_data["cookies"])
            except:
                self.cookie_jar = CookieJar()
            if isinstance(self.client, ClientSession) and (not self.client.closed):
                await self.client.close()
            self.client = None
        if self.client == None:
            timeout = ClientTimeout(total=5.0)
            self.client = ClientSession(cookie_jar=self.cookie_jar, timeout=timeout)
        await self.update_info()

    async def close(self):
        if isinstance(self.client, ClientSession) and (not self.client.closed):
            await self.client.close()
            self.client = None
        if isinstance(self.cookie_jar, CookieJar):
            save_data = {
                "cookies": cookiejar_to_dict(self.cookie_jar),
            }
            with open(self.save_path, "w") as f:
                json.dump(save_data, f)

    async def __aenter__(self) -> "MemobirdClient":
        await self.init()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def get(self, url, data):
        async with self.client.get(url, params=data) as resp:
            data = await resp.text()
            update_cookies(self.cookie_jar, resp)
            return json.loads(data)
    
    async def post(self, url, data):
        async with self.client.post(url, data=data) as resp:
            data = await resp.text()
            update_cookies(self.cookie_jar, resp)
            return json.loads(data)
    
    async def upload(self, url, params, data):
        async with self.client.post(url, params=params, data=data) as resp:
            data = await resp.text()
            update_cookies(self.cookie_jar, resp)
            return json.loads(data)
    
    async def login(self, phone: str, passwd: str):
        resp = await self.post(MB_INTERFACE_URL, {
            "DataType": "webLogin",
            "userCode": phone,
            "strUserPwd": passwd,
        })
        if int(resp.get("code", "0")) == 1:
            await self.update_info()
            return True
        return False
    
    async def get_qr_code(self):
        resp = await self.post(MB_INTERFACE_URL, {
            "DataType": "getScanCode",
            "parameter": "",
        })
        self.qr_parameter = resp["parameter"]
        return urljoin(MB_INTERFACE_URL, resp["url"])
    
    async def get_qr_result(self):
        """ * :return: int
                -1: 二维码过期
                 0: 还未登录
                 1: 登录成功
        """
        resp = await self.post(MB_INTERFACE_URL, {
            "DataType": "verifyWebQRCode",
            "parameter": self.qr_parameter,
        })
        if int(resp.get("auth", "0")) == 1:
            return 1
        if int(resp.get("expire", "0")) == 1:
            return -1
        return 0
    
    async def login_with_qr(self):
        image_link = await self.get_qr_code()
        print(f"请用浏览器访问以下图片, 并使用手机扫码登录:")
        print(image_link)
        print()
        while True:
            await asyncio.sleep(1)
            result = await self.get_qr_result()
            if result < 0:
                image_link = await self.get_qr_code()
                print(f"请用浏览器访问以下图片, 并使用手机扫码:")
                print(image_link)
                print()
            if result > 0:
                await self.update_info()
                print("登录成功")
                return
    
    async def logout(self):
        resp = await self.get(MB_INTERFACE_URL, { "DataType": "QuitWeb" })
        if int(resp.get("code", "0")) == 1:
            self.user_id = ""
            self.user_name = ""
            self.qr_parameter = ""
            self.devices.clear()
            return True
        return False
    
    async def update_info(self):
        resp = await self.get(MB_INTERFACE_URL, { "DataType": "LoginWeb" })
        if int(resp.get("code", "0")) != 1:
            return
        self.user_id = resp["userId"]
        self.user_name = resp["userName"]
        self.devices = []
        for device in resp["smartCores"]:
            self.devices.append((device["smartName"], device["smartGuid"]))
    
    async def print_html(self, content_html: str, device_index=0):
        if device_index >= len(self.devices) or device_index < 0:
            return False
        device_guid = self.devices[device_index][1]
        resp = await self.post(MB_INTERFACE_URL, {
            "DataType": "PrintPaper",
            "fromUserName": self.user_name,
            # "toUserName": self.user_name,
            "toUserName": "我",
            "toUserId": self.user_id,
            "guidList": device_guid,
            "printContent": content_html,
        })
        return int(resp.get("code", "0")) == 1

    async def upload_image(self, image_path):
        form = FormData()
        form.add_field("upfile", open(image_path, "rb"), filename=Path(image_path).name)
        params = { "action": "uploadimage" }
        resp = await self.upload(MB_IMAGE_UPLOAD_URL, params, form)
        url = resp.get("url", "")
        if url:
            return urljoin(MB_IMAGE_UPLOAD_URL, "/cn" + url)
        return ""

HTML_PREVIEW = """<!DOCTYPE html>
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8" />
        <style>
            * {
                padding: 0;
                margin: 0;
            }
            html {
                background-color: gray;
                width: 100%;
                height: 100%;
            }
            body {
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                width: 100%;
                height: 100%;
            }
            #_body_ {
                box-sizing: border-box;
                background-color: white;
                padding: 32px 16px;
                max-height: 100%;
                overflow-y: auto;
                overflow-x: hidden;
            }
            #_content_ {
                border: 1px dotted black;
                width: 384px;
                box-sizing: content-box;
            }
        </style>
    </head>
    <body>
        <div id="_body_">
            <div id="_content_">
                {CONTENT}
            </div>
        </div>
    </body>
</html>
"""

class PaperItem:
    @classmethod
    def get_style_html(cls) -> str:
        """ * :return: str
                返回该类对象公共的style html字符串
        """
        raise NotImplementedError

    def get_html(self) -> str:
        """ * :return: str
                返回该对象生成的html字符串
        """
        raise NotImplementedError

class PaperItemText(PaperItem):
    def __init__(self, text: str) -> None:
        """ 文本元素
            * :text: 文本内容
        """
        super().__init__()
        self.text = text
    
    @classmethod
    def get_style_html(_) -> str:
        return "<style>p._paper_text_ { overflow-wrap: break-word; }</style>"
    
    def get_html(self) -> str:
        return  "<p class=\"_paper_text_\">" \
                + escape(self.text) \
                .replace("\r", "") \
                .replace("\n", "<br />") + \
                "</p>"

class PaperItemImage(PaperItem):
    def __init__(self, src: str) -> None:
        """ 图片元素
            * :src: 图片源地址, 需要提前转义特殊字符
        """
        super().__init__()
        self.src = src
    
    @classmethod
    def get_style_html(_) -> str:
        return "<style>img._paper_img_ { max-width: 100%; }</style>"
    
    def get_html(self) -> str:
        return  f"<img class=\"_paper_img_\" src=\"{self.src}\" />"

class Paper:
    def __init__(self, width=384) -> None:
        """ 纸张对象
            * :width: 打印机分辨率, 默认384, 某些型号是576
        """
        self.width = width
        self.content: list[PaperItem] = []
        pass

    def append(self, item: PaperItem):
        assert isinstance(item, PaperItem)
        self.content.append(item)
    
    def append_text(self, text: str):
        self.content.append(PaperItemText(text))

    def append_image(self, src: str):
        self.content.append(PaperItemImage(src))

    def get_html(self) -> str:
        all_types = []
        for elem in self.content:
            cls = type(elem)
            if cls not in all_types:
                all_types.append(cls)
        styles = "\n".join((cls.get_style_html() for cls in all_types))
        contents = "\n".join((item.get_html() for item in self.content))
        return  "<div id=\"_paper_\"><style>" \
                f"#_paper_ {{ overflow: hidden; width: {self.width}px;}}" \
                f"#_paper_ * {{ max-width: 100%; }}" \
                "</style>" + styles + contents + \
                "</div>"

    def get_preview_html(self):
        return  HTML_PREVIEW \
                .replace("{WIDTH}", str(self.width)) \
                .replace("{CONTENT}", self.get_html())
