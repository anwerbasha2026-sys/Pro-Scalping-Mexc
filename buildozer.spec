[app]
title = Pro Scalping Mexc
package.name = proscalpingmexc
package.domain = com.proscalpingmexc
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,json,txt,ttf
source.exclude_dirs = tests,__pycache__,.github,.buildozer,bin
version = 1.1.0
requirements = python3,kivy==2.3.1,requests==2.32.5,plyer,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE,WAKE_LOCK,POST_NOTIFICATIONS
android.api = 33
android.minapi = 21
android.ndk = 28c
android.ndk_api = 21
android.archs = arm64-v8a,armeabi-v7a
android.enable_androidx = True
android.entrypoint = org.kivy.android.PythonActivity
services = scanner:service.py:foreground
android.accept_sdk_license = True
android.private_storage = True
android.debug_artifact = apk
p4a.bootstrap = sdl2
p4a.branch = develop
p4a.commit = 0382d27

[buildozer]
log_level = 2
warn_on_root = 1
