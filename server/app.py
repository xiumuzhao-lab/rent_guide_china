"""腾讯地图 API 代理服务 — 为前端看板提供 CORS 友好的人口地点搜索接口."""

import hashlib
import os
import time

from flask import Flask, jsonify, request
from urllib.parse import quote
import requests

app = Flask(__name__)

API_KEY = os.environ.get("TENCENT_MAP_KEY", "")
API_SK = os.environ.get("TENCENT_MAP_SK", "")

CACHE_TTL = 1800
CACHE_MAX_SIZE = 200
_cache = {}


@app.after_request
def add_cors(response):
    """为所有响应添加 CORS 头."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/tmap", methods=["GET", "OPTIONS"])
def tmap():
    """代理腾讯地图地点建议接口，带内存缓存."""
    if request.method == "OPTIONS":
        return "", 204

    if not API_KEY:
        return jsonify({"status": -1, "message": "TENCENT_MAP_KEY not configured"}), 500

    keyword = request.args.get("keyword", "")
    if not keyword:
        return jsonify({"status": -1, "message": "keyword required"}), 400

    entry = _cache.get(keyword)
    if entry and time.time() - entry["cached_at"] < CACHE_TTL:
        return entry["data"], entry["status"], {"Content-Type": "application/json"}

    uri = "/ws/place/v1/suggestion"
    params = {
        "keyword": keyword,
        "key": API_KEY,
        "region": "上海",
        "page_size": "5",
        "output": "json",
    }
    sorted_str = "&".join("{}={}".format(k, params[k]) for k in sorted(params))
    sig = hashlib.md5("{}?{}{}".format(uri, sorted_str, API_SK).encode()).hexdigest()
    encoded = "&".join("{}={}".format(k, quote(str(v), safe="")) for k, v in sorted(params.items()))
    url = "https://apis.map.qq.com{}?{}&sig={}".format(uri, encoded, sig)

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            if len(_cache) >= CACHE_MAX_SIZE:
                oldest = min(_cache, key=lambda k: _cache[k]["cached_at"])
                del _cache[oldest]
            _cache[keyword] = {
                "data": resp.content,
                "status": resp.status_code,
                "cached_at": time.time(),
            }
        return resp.content, resp.status_code, {"Content-Type": "application/json"}
    except Exception as e:
        return jsonify({"status": -1, "message": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8900)
