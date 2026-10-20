[app]
# Nombre de tu aplicación
title = Football Betting Analyzer

# Nombre del paquete
package.name = footballanalyzer
package.domain = org.probabilidadbotts

# Código fuente
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

# Punto de entrada principal
source.include_patterns = main.py, requirements.txt, src/*

# Versión
version = 1.0.0

# Requisitos / Dependencias de tu proyecto (extraídos de tu requirements.txt)
requirements = python3, kivy, requests, numpy, scipy, python-telegram-bot

# Permisos requeridos
permissions = INTERNET, ACCESS_NETWORK_STATE

# Configuración de pantalla
orientation = portrait
fullscreen = 0

# Requisitos de compilación de Android
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
