# -*- coding: utf-8 -*-
import random
import requests
import time
import re
import json
import math
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import bili_pb2

app = FastAPI()

user_agent_list = [
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) Gecko/20100101 Firefox/61.0",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.186 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.101 Safari/537.36",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/5.0 (Macintosh; U; PPC Mac OS X 10.5; en-US; rv:1.9.2.15) Gecko/20110303 Firefox/3.6.15",
]
headers = {'User-Agent': random.choice(user_agent_list)}

cache = {}
CRCPOLYNOMIAL = 0xEDB88320
crctable = [0 for _ in range(256)]


def create_table():
    for i in range(256):
        crcreg = i
        for _ in range(8):
            if (crcreg & 1) != 0:
                crcreg = CRCPOLYNOMIAL ^ (crcreg >> 1)
            else:
                crcreg = crcreg >> 1
        crctable[i] = crcreg


create_table()


def crc32(string):
    crcstart = 0xFFFFFFFF
    for i in range(len(str(string))):
        index = (crcstart ^ ord(str(string)[i])) & 255
        crcstart = (crcstart >> 8) ^ crctable[index]
    return crcstart


def crc32_last_index(string):
    crcstart = 0xFFFFFFFF
    for i in range(len(str(string))):
        index = (crcstart ^ ord(str(string)[i])) & 255
        crcstart = (crcstart >> 8) ^ crctable[index]
    return index


def get_crc_index(t):
    for i in range(256):
        if crctable[i] >> 24 == t:
            return i
    return -1


def deep_check(i, index):
    string = ""
    hashcode = crc32(i)
    tc = hashcode & 0xff ^ index[2]
    if not (57 >= tc >= 48):
        return [0]
    string += str(tc - 48)
    hashcode = crctable[index[2]] ^ (hashcode >> 8)
    tc = hashcode & 0xff ^ index[1]
    if not (57 >= tc >= 48):
        return [0]
    string += str(tc - 48)
    hashcode = crctable[index[1]] ^ (hashcode >> 8)
    tc = hashcode & 0xff ^ index[0]
    if not (57 >= tc >= 48):
        return [0]
    string += str(tc - 48)
    return [1, string]


def crack(danmu):
    index = [0 for _ in range(4)]
    i = 0
    ht = int(f"0x{danmu['midHash']}", 16) ^ 0xffffffff
    for i in range(3, -1, -1):
        index[3 - i] = get_crc_index(ht >> (i * 8))
        snum = crctable[index[3 - i]]
        ht ^= snum >> ((3 - i) * 8)
    for i in range(100000000):
        lastindex = crc32_last_index(i)
        if lastindex == index[3]:
            deepCheckData = deep_check(i, index)
            if deepCheckData[0]:
                break
    if i == 100000000:
        return -1
    danmu['mid'] = f"{i}{deepCheckData[1]}"


class BVRequest(BaseModel):
    videosrc: str
    keyword: str


@app.get("/")
def _():
    return FileResponse('./html/index.html')


class DanmuResult(BaseModel):
    danmu: str
    userid: str


@app.post("/get_user_id")
def get_user_id(request: BVRequest) -> list[DanmuResult]:
    try:
        bvid = get_bvid(request.videosrc)
        keyword = request.keyword
        info = get_info(bvid)
        cid = info["cid"]
        duration = info["duration"]
        ls = []
        for i in range(math.ceil(duration / (60 * 6))):
            all_danmu = get_danmu(cid, i+1)
            for danmu in all_danmu:
                if keyword in danmu['content']:
                    crack(danmu)
                    ls.append(DanmuResult(danmu=danmu['content'], userid=danmu['mid']))
                    return ls
        return ls
    except Exception:
        raise HTTPException(500)


def get_bvid(url):
    """
    获取一般视频、分P视频的bvid

    :param url: 视频地址
    :return: 视频bvid
    """

    bvid = re.search(r'(BV.*?).{10}', url)
    return bvid.group(0)


def get_info(bvid):
    data = requests.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                        headers=headers).text

    data = json.loads(data)["data"]
    video_num = data["videos"]
    title = data["title"]

    pub_time = time.strftime("%Y-%m-%d", time.localtime(data["pubdate"]))

    desc = data["desc"]
    danmuku = data["stat"]["danmaku"]
    name = data["owner"]["name"]
    cid = data["cid"]
    duration = data["duration"]

    dict_info = {"title": title, "pub_time": pub_time, "desc": desc,
                 "danmuku": danmuku, "name": name, "cid": cid, "duration": duration}
    if int(video_num) == 1:
        return dict_info
    else:
        return dict_info  # Simplified for API usage


def get_danmu(cid, segment_index):
    all_danmu = []

    global cached
    if (cached := cache.get(cid)):
        # cached['lastupdtime']
        pass

    url = f'https://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index={segment_index}'
    resp = requests.get(url, headers=headers)
    data = resp.content

    danmaku_seg = bili_pb2.DmSegMobileReply()
    danmaku_seg.ParseFromString(data)

    mode_list = ["普通弹幕", "普通弹幕", "普通弹幕", "普通弹幕", "底部弹幕", "顶部弹幕", "逆向弹幕", "高级弹幕",
                 "代码弹幕", "BAS弹幕（仅限于特殊弹幕专包）"]
    for danmu in danmaku_seg.elems:
        ctime = time.localtime(danmu.ctime)
        add = {"midHash": danmu.midHash, "content": danmu.content, "ctime": time.strftime("%Y-%m-%d %H:%M:%S", ctime),
               "fontsize": danmu.fontsize, "mode": mode_list[danmu.mode], "id": danmu.idStr}
        all_danmu.append(add)
    cache[cid] = {'lastupdtime': time.time(), 'danmu': all_danmu}
    return all_danmu


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
