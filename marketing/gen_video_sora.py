#!/usr/bin/env python3
"""Generate video Sora-2 (Sumopod /v1/videos) lan download asil.
POST → poll → download. OpenAI-compatible.
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = "https://ai.sumopod.com/v1/videos"
KEY = os.environ.get("HERMES_CUSTOM_AI_SUMOPOD_COM_API_KEY", "")

def call(method, url, body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {KEY}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:800]}

if __name__ == "__main__":
    prompt = (
        "Vertical 9:16 TikTok advertisement video for a natural herbal jamu product: "
        "an elegant amber glass bottle of herbal tonic on a rustic wooden table, "
        "surrounded by fresh turmeric roots, ginger, lemongrass and green leaves, "
        "golden honey slowly dripping into a small glass cup beside it, gentle steam rising, "
        "water droplets on the cool bottle surface, lush green herbal garden softly blurred in background, "
        "warm sunlight, cinematic product photography, premium healthy lifestyle aesthetic, "
        "appetizing and clean, smooth slow camera push-in, high detail, 5 seconds"
    )
    candidates = [
        "sora-2-pro-2025-10-06",
        "sora-2-pro",
        "sora-2-2025-12-08",
        "sora-2-2025-10-06",
        "sora-2",
    ]
    resp = None
    for model in candidates:
        body = {"model": model, "prompt": prompt, "size": "720x1280", "duration": 5}
        print(f">> POST /v1/videos model={model} ...")
        resp = call("POST", BASE, body)
        if "_http_error" not in resp:
            print(f">> Model ACCEPTED: {model}")
            break
        print(f"   ditolak: {resp.get('_body', '')[:200]}")
    if not resp or "_http_error" in resp:
        print("!! Kabeh kandidat ditolak")
        sys.exit(1)
    vid = resp.get("id") or resp.get("video_id") or resp.get("data", {}).get("id")
    if not vid:
        print("!! Ora entuk video id:", resp)
        sys.exit(1)
    print(f"\n>> Video ID: {vid} — polling status...")
    url = None
    for i in range(60):  # maks 10 menit
        time.sleep(10)
        st = call("GET", f"{BASE}/{vid}")
        status = st.get("status") or st.get("state") or ""
        print(f"   [{i+1}] status={status}")
        if status in ("completed", "succeeded", "success", "complete"):
            url = st.get("mp4_url") or st.get("url") or st.get("video_url") or \
                  (st.get("outputs") or [{}])[0].get("url")
            break
        if status in ("failed", "error", "cancelled"):
            print("!! Gagal:", json.dumps(st, indent=2)[:800])
            sys.exit(1)
    if not url:
        print("!! Timeout polling")
        sys.exit(1)
    print(f">> Download: {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as r, open("/tmp/sora_herbal_tiktok.mp4", "wb") as f:
        f.write(r.read())
    print(">> Siap: /tmp/sora_herbal_tiktok.mp4")
