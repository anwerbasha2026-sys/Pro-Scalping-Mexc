[app]

title = Pro Scalping Mexc
package.name = proscalpingmexc
package.domain = com.proscalpingmexc

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,json,txt,ttf

version = 1.0.4

requirements = python3,kivy==2.3.1,requests==2.32.5,plyer,jnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION,FOREGROUND_SERVICE,WAKE_LOCK,POST_NOTIFICATIONS

android.api = 33
android.minapi = 21

android.ndk = 28c
android.ndk_api = 21
android.archs = armeabi-v7a

android.enable_androidx = True
android.entrypoint = org.kivy.android.PythonActivity

services = scanner:service.py:foreground

android.accept_sdk_license = True
android.private_storage = True
android.debug_artifact = apk

p4a.bootstrap = sdl2

[buildozer]

log_level = 2
warn_on_root = 1
