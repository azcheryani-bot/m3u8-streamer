import argparse
import os
import time
import json
import threading
import subprocess
import glob
import signal
import sys
import shutil
import boto3
from botocore.client import Config

# آدرس صفحه‌ای که می‌خواهید استریم شود
TARGET_URL = "https://kheyriyeh2.hudsonparker87.workers.dev/display"

# مشخصات اتصال به باکت استوریج نئون
S3_ENDPOINT = "https://br-lucky-wave-axbfuzrm.storage.c-4.us-east-2.aws.neon.tech"
S3_ACCESS_KEY = "nak_live_1bfd6791115643c59cee64e82e36e1cd"
S3_SECRET_KEY = "nsk_live_a15238f9642107cd7482831f8d003dfbf6d2bdcae52bb44b099eb321a74c60a7"
S3_REGION = "us-east-2"
BUCKET_NAME = "m3u8-streamer"

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION,
    config=Config(signature_version='s3v4')
)

def purge_bucket():
    print("🧹 در حال پاک‌سازی باکت نئون...")
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
        if 'Contents' in response:
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            s3_client.delete_objects(Bucket=BUCKET_NAME, Delete={'Objects': objects_to_delete})
            print("✨ باکت نئون تخلیه شد.")
    except Exception as e:
        print(f"⚠️ پیام وضعیت باکت: {e}")

def s3_sync_worker(stop_event):
    uploaded_files = set()
    print("☁️ همگام‌ساز خودکار به حافظه ابری نئون فعال شد.")
    while not stop_event.is_set():
        for ts_file in glob.glob("*.ts"):
            if ts_file not in uploaded_files and os.path.exists(ts_file):
                try:
                    s3_client.upload_file(
                        ts_file, BUCKET_NAME, ts_file,
                        ExtraArgs={
                            'ContentType': 'video/MP2T',
                            'CacheControl': 'no-cache, no-store, must-revalidate, max-age=0'
                        }
                    )
                    uploaded_files.add(ts_file)
                except Exception:
                    pass
        
        if os.path.exists("live.m3u8"):
            try:
                s3_client.upload_file(
                    "live.m3u8", BUCKET_NAME, "live.m3u8",
                    ExtraArgs={
                        'ContentType': 'application/vnd.apple.mpegurl',
                        'CacheControl': 'no-cache, no-store, must-revalidate, max-age=0'
                    }
                )
            except Exception:
                pass

        time.sleep(0.5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quality', required=True)
    parser.add_argument('--fps', required=True, type=int)
    parser.add_argument('--duration', required=True, type=int)
    args = parser.parse_args()

    qualities = {
        '240p': ('426x240', 426, 240, '500k'),
        '360p': ('640x360', 640, 360, '800k'),
        '480p': ('854x480', 854, 480, '1200k'),
        '720p': ('1280x720', 1280, 720, '2500k'),
        '1080p': ('1920x1080', 1920, 1080, '4500k'),
        '1440p': ('2560x1440', 2560, 1440, '9000k')
    }
    resolution_str, width, height, bitrate = qualities.get(args.quality, qualities['720p'])
    fps = args.fps

    # ۱. پاک‌سازی اولیه فایل‌های لوکال و باکت نئون
    for f in glob.glob("*.ts") + glob.glob("*.m3u8"):
        try: os.remove(f)
        except: pass
    purge_bucket()

    # ۲. ایجاد مانیتور مجازی دقیقاً به ابعاد رزولوشن انتخاب‌شده
    os.environ["DISPLAY"] = ":99"
    subprocess.Popen(['Xvfb', ':99', '-screen', '0', f'{width}x{height}x24', '-ac'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

    # ۳. آماده‌سازی پروفایل کاربری کروم و غیرفعال‌سازی قطعی نوار ترجمه
    profile_dir = f"/tmp/clean_chrome_profile_{width}x{height}"
    default_dir = os.path.join(profile_dir, "Default")
    os.makedirs(default_dir, exist_ok=True)
    
    prefs = {
        "translate": {"enabled": False},
        "translate_blocked_languages": ["fa", "en", "ar", "und"],
        "intl": {"accept_languages": "fa,en-US,en"}
    }
    with open(os.path.join(default_dir, "Preferences"), "w") as f:
        json.dump(prefs, f)

    browser_executable = shutil.which('google-chrome') or shutil.which('chromium-browser') or 'google-chrome'

    # ۴. باز کردن آدرس آنلاین به صورت تمام‌صفحه و تمیز
    chrome_cmd = [
        browser_executable,
        '--kiosk',
        '--no-sandbox',
        '--disable-infobars',
        '--disable-dev-shm-usage',
        '--disable-translate',
        '--disable-features=Translate,OptimizationHints,MediaRouter,CalculateNativeWinOcclusion',
        '--no-first-run',
        '--no-default-browser-check',
        '--hide-scrollbars',
        '--window-position=0,0',
        f'--window-size={width},{height}',
        f'--user-data-dir={profile_dir}',
        TARGET_URL
    ]
    subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)  # زمان لازم برای لود کامل صفحه اینترنتی و برقراری ارتباطات

    # ۵. ضبط تصویر بدون نشانگر ماوس
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-f', 'x11grab',
        '-draw_mouse', '0',
        '-video_size', f'{width}x{height}',
        '-framerate', str(fps),
        '-i', ':99.0',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-b:v', bitrate,
        '-maxrate', bitrate,
        '-bufsize', str(int(bitrate.replace('k',''))*2) + 'k',
        '-pix_fmt', 'yuv420p',
        '-g', str(fps * 2),
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '5',
        '-hls_flags', 'delete_segments',
        'live.m3u8'
    ]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ۶. فعال‌سازی آپلود به نئون
    stop_event = threading.Event()
    uploader_thread = threading.Thread(target=s3_sync_worker, args=(stop_event,), daemon=True)
    uploader_thread.start()

    neon_stream_url = f"{S3_ENDPOINT}/{BUCKET_NAME}/live.m3u8"
    print("\n" + "="*60)
    print(f"🚀 استریم صفحه آنلاین در کیفیت {args.quality} ({width}x{height}) آغاز شد!")
    print(f"🌐 آدرس در حال پخش: {TARGET_URL}")
    print(f"🔗 آدرس خروجی استریم: {neon_stream_url}")
    print("="*60 + "\n")

    def cleanup_and_exit(signum=None, frame=None):
        print("\n🛑 دستور توقف دریافت شد. در حال قطع استریم...")
        stop_event.set()
        try:
            ffmpeg_proc.terminate()
        except:
            pass
        purge_bucket()
        print("✅ استریم متوقف و باکت نئون تخلیه شد.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    end_time = time.time() + (args.duration * 60)
    while time.time() < end_time:
        time.sleep(1)

    cleanup_and_exit()

if __name__ == "__main__":
    main()
