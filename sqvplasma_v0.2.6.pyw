import sys
import os
import json
import subprocess
import importlib.util
import requests
import shutil
import ctypes
import webbrowser
import zipfile
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QLineEdit, 
                             QVBoxLayout, QWidget, QLabel, QHBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt, QPoint, QTimer, QSize, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QTextCursor, QTextCharFormat, QCursor

# Конфигурационные файлы
PACKAGES_FILE = "packages.json"
PROGRAMS_FILE = "programs.json"
CONFIG_FILE = "config.json"
PAC_DIR = "pac"  # Папка для установленных пакетов

# Создаем папку для пакетов, если ее нет
Path(PAC_DIR).mkdir(exist_ok=True)

# Список защищенных системных папок
PROTECTED_PATHS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    "C:\\System Volume Information",
    "C:\\$Recycle.Bin",
    "C:\\Recovery",
    "C:\\Boot",
    "C:\\PerfLogs",
    "C:\\Users\\Default",
    "C:\\Documents and Settings",
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64"
]

class InstallerTracker(QThread):
    finished = pyqtSignal(str, str)  # Сигнал: имя приложения, путь к установщику

    def __init__(self, process, app_name, installer_path):
        super().__init__()
        self.process = process
        self.app_name = app_name
        self.installer_path = installer_path

    def run(self):
        self.process.wait()  # Ожидаем завершения процесса
        self.finished.emit(self.app_name, self.installer_path)

class CommandLine:
    def __init__(self):
        self.packages = self.load_data(PACKAGES_FILE)
        self.programs = self.load_data(PROGRAMS_FILE)
        self.config = self.load_data(CONFIG_FILE) or {
            "tcmd_active": False,
            "theme": "dark"
        }
        self.loaded_packages = {}  # Загруженные модули пакетов
        self.current_dir = os.getcwd()
        self.installer_trackers = {}
        
        # Загрузка установленных пакетов
        self.load_installed_packages()
        
        # Контекст для выполнения Python кода
        self.python_context = {
            "__builtins__": __builtins__,
            "os": os,
            "sys": sys,
            "json": json,
            "requests": requests,
            "shutil": shutil,
            "ctypes": ctypes,
            "webbrowser": webbrowser,
            "subprocess": subprocess,
            "cli": self  # Доступ к самому объекту CLI
        }
        
    def load_installed_packages(self):
        """Динамическая загрузка установленных пакетов"""
        # Загружаем все .pyw файлы из папки pac
        for filename in os.listdir(PAC_DIR):
            if filename.endswith(".pyw"):
                package_name = filename[:-4]
                self.load_package(package_name)
            
    def load_package(self, package_name):
        """Загрузка конкретного пакета"""
        try:
            # Формируем путь к файлу пакета
            package_path = os.path.join(PAC_DIR, f"{package_name}.pyw")
            
            # Проверяем существование файла
            if not os.path.exists(package_path):
                print(f"Файл пакета {package_name} не найден: {package_path}")
                return
                
            # Динамическая загрузка модуля
            spec = importlib.util.spec_from_file_location(package_name, package_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Сохраняем загруженный модуль
            self.loaded_packages[package_name] = module
            print(f"Пакет {package_name} успешно загружен")
            
        except Exception as e:
            print(f"Ошибка загрузки пакета {package_name}: {e}")
    
    def load_data(self, filename):
        """Загрузка данных из JSON-файла"""
        try:
            if Path(filename).exists():
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки {filename}: {e}")
        return {}

    def save_data(self, data, filename):
        """Сохранение данных в JSON-файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения {filename}: {e}")
            return False

    def execute_command(self, command):
        """Выполнение команды и возврат результата"""
        parts = command.split()
        if not parts:
            return ""
            
        cmd = parts[0].lower()
        args = parts[1:]
        
        # Основные команды
        if cmd == "pacman":
            return self.handle_pacman(args)
        elif cmd == "print":
            return ' '.join(args)
        elif cmd == "start":
            return self.handle_start(args)
        elif cmd == "tcmd":
            return self.handle_tcmd(args)
        elif cmd == "help":
            return self.get_help()
        elif cmd == "exit":
            QApplication.quit()
            return "Завершение работы..."
        elif cmd == "clear":
            return "clear"
        elif cmd == "app":
            return self.handle_app(args)
        elif cmd == "rm":
            return self.handle_rm(args)
        elif cmd == "py" or cmd == "python":
            return self.handle_python(' '.join(args))
        elif cmd == "pip":
            return self.handle_pip(args)
        elif cmd == "run":
            return self.handle_run(args)
        
        # Обработка команд из установленных пакетов
        for package_name, package_module in self.loaded_packages.items():
            if hasattr(package_module, 'handle_command'):
                result = package_module.handle_command(cmd, args)
                if result is not None:
                    return result
        
        return f"Неизвестная команда: {cmd}. Введите 'help' для справки"

    def handle_pacman(self, args):
        """Обработчик пакетного менеджера"""
        if not args:
            return "Использование: pacman [list|install|delete|reinstall|update] ..."
            
        action = args[0]
        
        if action == "list":
            # Список установленных пакетов
            if not self.packages:
                return "Нет установленных пакетов"
            return "\n".join(self.packages.keys())
        
        if len(args) < 2:
            return f"Недостаточно аргументов для команды: pacman {action}"
            
        package = args[1]
        
        if action == "install":
            # URL для скачивания пакета
            package_url = self.get_package_url(package)
            
            if not package_url:
                return f"URL для пакета {package} не настроен"
                
            # Скачивание и установка пакета
            return self.install_package(package, package_url)
            
        elif action == "delete":
            if package in self.packages:
                # Удаление пакета
                return self.uninstall_package(package)
            return f"Пакет '{package}' не найден"
                
        elif action == "reinstall":
            if package in self.packages:
                # Переустановка пакета
                package_url = self.packages[package].get("url", "")
                if not package_url:
                    return f"URL для пакета {package} не найден"
                    
                # Сначала удаляем, потом устанавливаем
                self.uninstall_package(package)
                return self.install_package(package, package_url)
            return f"Пакет '{package}' не найден"
                
        elif action == "update":
            if package in self.packages:
                # Обновление пакета
                package_url = self.packages[package].get("url", "")
                if not package_url:
                    return f"URL для пакета {package} не найден"
                    
                return self.install_package(package, package_url)
            return f"Пакет '{package}' не найден"
                
        return f"Неизвестная операция: {action}"

    def get_package_url(self, package_name):
        """Получение URL для пакета"""
        package_urls = {
            "FileTools": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/FileTools.pyw",
            "NetworkUtils": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/NetworkUtils.pyw",
            "SystemMonitor": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/SystemMonitor.pyw",
            "DevTools": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/DevTools.pyw",
            "Customization": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/Customization.pyw",
            "TCMD": "https://raw.githubusercontent.com/sqvs/sqvplasma-packages/refs/heads/main/pac/TCMD.pyw"
        }
        return package_urls.get(package_name, "")

    def install_package(self, package_name, package_url):
        """Установка пакета из URL"""
        try:
            # Скачивание пакета
            response = requests.get(package_url)
            response.raise_for_status()
            
            # Сохранение в папку pac
            package_path = os.path.join(PAC_DIR, f"{package_name}.pyw")
            with open(package_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            # Добавление информации о пакете
            self.packages[package_name] = {
                "version": "1.0",
                "status": "installed",
                "url": package_url
            }
            self.save_data(self.packages, PACKAGES_FILE)
            
            # Загрузка пакета
            self.load_package(package_name)
            
            return f"Пакет '{package_name}' успешно установлен"
        except Exception as e:
            return f"Ошибка установки пакета: {e}"

    def uninstall_package(self, package_name):
        """Удаление пакета"""
        try:
            # Удаление файла пакета
            package_path = os.path.join(PAC_DIR, f"{package_name}.pyw")
            if os.path.exists(package_path):
                os.remove(package_path)
            
            # Удаление из списка пакетов
            if package_name in self.packages:
                del self.packages[package_name]
                self.save_data(self.packages, PACKAGES_FILE)
            
            # Удаление из загруженных модулей
            if package_name in self.loaded_packages:
                del self.loaded_packages[package_name]
            
            return f"Пакет '{package_name}' удалён"
        except Exception as e:
            return f"Ошибка удаления пакета: {e}"

    def handle_start(self, args):
        """Запуск программ"""
        if not args:
            return "Использование: start <имя_программы>"
            
        program = args[0]
        if program in self.programs:
            try:
                subprocess.Popen(self.programs[program], shell=True)
                return f"Программа '{program}' запущена"
            except Exception as e:
                return f"Ошибка запуска: {e}"
        return f"Программа '{program}' не зарегистрирована"

    def handle_tcmd(self, args):
        """Обработчик команд TCMD"""
        if not args:
            return "Использование: tcmd [activate|deactivate]"
            
        if args[0].lower() == "activate":
            self.config["tcmd_active"] = True
            self.save_data(self.config, CONFIG_FILE)
            return "TCMD эффекты активированы. Перезапуск приложения..."
            
        elif args[0].lower() == "deactivate":
            self.config["tcmd_active"] = False
            self.save_data(self.config, CONFIG_FILE)
            return "TCMD эффекты деактивированы. Перезапуск приложения..."
            
        return f"Неизвестная команда TCMD: {args[0]}"

    def handle_app(self, args):
        """Установка приложений"""
        if not args:
            return "Использование: app [install|list] ..."
            
        if args[0] == "install" and len(args) >= 2:
            app_name = args[1].lower()
            return self.install_application(app_name)
            
        elif args[0] == "list":
            return self.list_applications()
            
        return f"Неизвестная команда app: {' '.join(args)}"
    
    def list_applications(self):
        """Список доступных приложений"""
        applications = self.get_applications_list()
        categories = {}
        
        for app, details in applications.items():
            category = details.get("category", "Другие")
            if category not in categories:
                categories[category] = []
            categories[category].append(app)
        
        result = "Доступные приложения:\n"
        for category, apps in categories.items():
            result += f"\n{category}:\n"
            result += ", ".join(apps)
        
        return result
    
    def get_applications_list(self):
        """Список поддерживаемых приложений"""
        return {
            # VPN сервисы
            "expressvpn": {"url": "https://www.expressvpn.com/latest?utm_source=windows", "category": "VPN сервисы"},
            "nordvpn": {"url": "https://downloads.nordcdn.com/apps/windows/10/NordVPN/latest/NordVPNSetup.exe", "category": "VPN сервисы"},
            "surfshark": {"url": "https://downloads.surfshark.com/windows/client/win/Surfshark-Setup-latest.exe", "category": "VPN сервисы"},
            "cyberghostvpn": {"url": "https://download.cyberghostvpn.com/8.0.3.30/setup/CyberGhost.8.0.3.30_setup.exe", "category": "VPN сервисы"},
            "protonvpn": {"url": "https://protonvpn.com/download/ProtonVPN_v3.0.0.exe", "category": "VPN сервисы"},
            
            # Медиаплееры и стриминги
            "spotify": {"url": "https://download.scdn.co/SpotifySetup.exe", "category": "Медиаплееры и стриминги"},
            "itunes": {"url": "https://www.apple.com/itunes/download/win64", "category": "Медиаплееры и стриминги"},
            "vlc": {"url": "https://get.videolan.org/vlc/last/win64/vlc-3.0.16-win64.exe", "category": "Медиаплееры и стриминги"},
            "winamp": {"url": "https://www.oldversion.com/windows/winamp-5-666/", "category": "Медиаплееры и стриминги"},
            
            # Торрент-клиенты
            "qbittorrent": {"url": "https://www.fosshub.com/qBittorrent.html?dwl=qbittorrent_4.4.5_setup.exe", "category": "Торрент-клиенты"},
            "deluge": {"url": "https://ftp.osuosl.org/pub/deluge/windows/deluge-2.1.1-win64-py3.10.exe", "category": "Торрент-клиенты"},
            "utorrent": {"url": "https://download.utorrent.com/utorrent/utorrent.exe", "category": "Торрент-клиенты"},
            "bittorent": {"url": "https://download-new.utorrent.com/endpoint/bittorrent/os/windows/track/stable", "category": "Торрент-клиенты"},
            
            # Мессенджеры
            "whatsapp": {"url": "https://web.whatsapp.com/desktop/windows/release/x64/WhatsAppSetup.exe", "category": "Мессенджеры"},
            "signal": {"url": "https://updates.signal.org/desktop/signal-desktop-win-1.40.5.exe", "category": "Мессенджеры"},
            "telegram": {"url": "https://telegram.org/dl/desktop/win", "category": "Мессенджеры"},
            "discord": {"url": "https://discord.com/api/downloads/distributions/app/installers/latest?channel=stable&platform=win&arch=x86", "category": "Мессенджеры"},
            "discord-ptb": {"url": "https://discord.com/api/downloads/distributions/app/installers/latest?channel=ptb&platform=win&arch=x86", "category": "Мессенджеры"},
            "discord-canary": {"url": "https://discord.com/api/downloads/distributions/app/installers/latest?channel=canary&platform=win&arch=x86", "category": "Мессенджеры"},
            
            # Инструменты разработчика
            "pycharm": {"url": "https://download.jetbrains.com/python/pycharm-professional-2021.3.2.exe", "category": "Инструменты разработчика"},
            "intellij-idea": {"url": "https://download.jetbrains.com/idea/ideaIU-2021.3.2.exe", "category": "Инструменты разработчика"},
            "android-studio": {"url": "https://redirector.gvt1.com/edgedl/android/studio/install/2021.2.1.15/android-studio-2021.2.1.15-windows.exe", "category": "Инструменты разработчика"},
            "git": {"url": "https://github.com/git-for-windows/git/releases/download/v2.35.1.windows.2/Git-2.35.1.2-64-bit.exe", "category": "Инструменты разработчика"},
            "vscode": {"url": "https://code.visualstudio.com/sha/download?build=stable&os=win32-x64", "category": "Инструменты разработчика"},
            
            # Игровые платформы
            "steam": {"url": "https://cdn.cloudflare.steamstatic.com/client/installer/SteamSetup.exe", "category": "Игровые платформы"},
            "epic-games": {"url": "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi", "category": "Игровые платформы"},
            "origin": {"url": "https://www.dm.origin.com/download/OriginThinSetup.exe", "category": "Игровые платформы"},
            "battle-net": {"url": "https://www.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe", "category": "Игровые платформы"},
            
            # Системные утилиты
            "ccleaner": {"url": "https://download.ccleaner.com/ccsetup615.exe", "category": "Системные утилиты"},
            "winrar": {"url": "https://www.win-rar.com/fileadmin/winrar-versions/winrar/winrar-x64-611.exe", "category": "Системные утилиты"},
            "7-zip": {"url": "https://www.7-zip.org/a/7z2107-x64.exe", "category": "Системные утилиты"},
            "processhacker": {"url": "https://github.com/processhacker/processhacker/releases/download/v2.39/processhacker-2.39-setup.exe", "category": "Системные утилиты"},
            "extremeinjector": {"url": "https://github.com/master131/ExtremeInjector/releases/download/v3.7.3/Extreme.Injector.v3.7.3.zip", "category": "Системные утилиты"},
            "rainmeter": {"url": "https://github.com/rainmeter/rainmeter/releases/download/v4.5.17.3700/Rainmeter-4.5.17.exe", "category": "Системные утилиты"},
            
            # Офисные приложения
            "libreoffice": {"url": "https://download.documentfoundation.org/libreoffice/stable/7.3.2/win/x86_64/LibreOffice_7.3.2_Win_x86-64.msi", "category": "Офисные приложения"},
            "openoffice": {"url": "https://sourceforge.net/projects/openofficeorg.mirror/files/4.1.11/binaries/en-US/Apache_OpenOffice_4.1.11_Win_x86_install_en-US.exe", "category": "Офисные приложения"},
            "adobe-acrobat-reader": {"url": "https://ardownload2.adobe.com/pub/adobe/reader/win/AcrobatDC/2200120140/AcroRdrDC2200120140_en_US.exe", "category": "Офисные приложения"},
            
            # Другие полезные приложения
            "teamviewer": {"url": "https://download.teamviewer.com/download/TeamViewer_Setup.exe", "category": "Другие приложения"},
            "zoom": {"url": "https://cdn.zoom.us/prod/5.10.4.2850/ZoomInstaller.exe", "category": "Другие приложения"},
            "skype": {"url": "https://download.skype.com/s4l/download/win/Skype-8.87.0.223.exe", "category": "Другие приложения"},
            "notepad++": {"url": "https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.3.3/npp.8.3.3.Installer.x64.exe", "category": "Другие приложения"},
            
            # Браузеры
            "firefox": {"url": "https://download.mozilla.org/?product=firefox-latest&os=win&lang=en-US", "category": "Браузеры"},
            "firefox-nightly": {"url": "https://download.mozilla.org/?product=firefox-nightly-latest-ssl&os=win&lang=en-US", "category": "Браузеры"},
            "edge": {"url": "https://go.microsoft.com/fwlink/?linkid=2109047&Channel=Stable&language=en", "category": "Браузеры"},
            "chromium": {"url": "https://download-chromium.appspot.com/dl/Win?type=snapshots", "category": "Браузеры"},
            "googlechrome": {"url": "https://dl.google.com/chrome/install/standalonesetup.exe", "category": "Браузеры"},
            "opera": {"url": "https://get.geo.opera.com/pub/opera/desktop/", "category": "Браузеры"},
            
            # Аудиоплееры
            "aimp": {"url": "https://www.aimp.ru/?do=download.file&id=26", "category": "Аудиоплееры"},
        }
    
    def install_application(self, app_name):
        """Установка указанного приложения"""
        applications = self.get_applications_list()
        
        if app_name not in applications:
            return f"Приложение '{app_name}' не поддерживается. Используйте 'app list' для списка доступных приложений"
            
        # Запрос подтверждения
        confirm = self.ask_confirmation(f"Вы уверены, что хотите установить {app_name}?")
        if not confirm:
            return "Установка отменена"
            
        # Скачивание установщика
        url = applications[app_name]["url"]
        try:
            # Для некоторых приложений требуется специальная обработка
            if app_name == "telegram":
                webbrowser.open(url)
                return f"Установщик Telegram открыт в браузере. Завершите установку вручную."
                
            if app_name == "extremeinjector":
                # Для ExtremeInjector скачиваем архив
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                filename = "ExtremeInjector.zip"
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Распаковываем архив
                with zipfile.ZipFile(filename, 'r') as zip_ref:
                    zip_ref.extractall("ExtremeInjector")
                
                os.remove(filename)
                return f"ExtremeInjector скачан и распакован в папку ExtremeInjector"
                
            # Скачиваем установщик
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Определяем имя файла
            if "content-disposition" in response.headers:
                content_disposition = response.headers["content-disposition"]
                filename = content_disposition.split("filename=")[1].strip('"')
            else:
                # Генерируем имя файла на основе имени приложения
                if ".exe" in url.lower():
                    filename = f"{app_name}_installer.exe"
                elif ".msi" in url.lower():
                    filename = f"{app_name}_installer.msi"
                else:
                    filename = f"{app_name}_installer.bin"
            
            # Сохраняем файл
            installer_path = os.path.abspath(filename)
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # фильтруем keep-alive новые chunks
                        f.write(chunk)
            
            # Запускаем установщик
            process = subprocess.Popen([installer_path], shell=True)
            
            # Создаем и запускаем трекер для отслеживания завершения установки
            tracker = InstallerTracker(process, app_name, installer_path)
            tracker.finished.connect(self.on_installer_finished)
            tracker.start()
            
            return f"Установщик {app_name} запущен. После завершения установки вам будет предложено удалить установщик."
            
        except Exception as e:
            return f"Ошибка установки {app_name}: {e}"
    
    def on_installer_finished(self, app_name, installer_path):
        """Обработка завершения установки"""
        # Создаем временное приложение для отображения диалога
        app = QApplication.instance() or QApplication(sys.argv)
        
        reply = QMessageBox.question(
            None,
            'Удаление установщика',
            f"Установка {app_name} завершена. Удалить установщик?\n{installer_path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            try:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                    # Отправляем сообщение в главное окно
                    if hasattr(self, 'window'):
                        self.window.output_area.append(f"Установщик удалён: {installer_path}")
            except Exception as e:
                if hasattr(self, 'window'):
                    self.window.output_area.append(f"Ошибка удаления установщика: {e}")
    
    def handle_rm(self, args):
        """Удаление файлов и папок"""
        if not args:
            return "Использование: rm [trb|nrb] <путь>"
            
        # Определяем режим удаления
        mode = "trb"  # По умолчанию в корзину
        path_index = 0
        
        if args[0].lower() in ["trb", "nrb"]:
            mode = args[0].lower()
            if len(args) < 2:
                return "Укажите путь для удаления"
            path = args[1]
            path_index = 1
        else:
            path = args[0]
        
        # Проверяем путь
        full_path = os.path.abspath(path)
        
        # Проверяем, не является ли путь защищенным
        for protected_path in PROTECTED_PATHS:
            if full_path.startswith(os.path.abspath(protected_path)):
                return f"Ошибка: Нельзя удалять системные файлы и папки ({protected_path})"
                
        # Запрос подтверждения
        confirm = self.ask_confirmation(f"Вы уверены, что хотите удалить '{full_path}'?")
        if not confirm:
            return "Удаление отменено"
            
        # Выполняем удаление
        try:
            if mode == "trb":
                return self.send_to_recycle_bin(full_path)
            else:  # nrb
                return self.permanent_delete(full_path)
        except Exception as e:
            return f"Ошибка удаления: {e}"
    
    def send_to_recycle_bin(self, path):
        """Отправка в корзину"""
        try:
            # Используем Windows API для отправки в корзину
            shell32 = ctypes.windll.shell32
            if os.path.isfile(path):
                shell32.SHFileOperationW(0, 0x0003, path, None, 1, 0, None)
            elif os.path.isdir(path):
                shell32.SHFileOperationW(0, 0x0003, path + "\\*.*", None, 1, 0, None)
            return f"Отправлено в корзину: {path}"
        except:
            return "Ошибка: Не удалось отправить в корзину"
    
    def permanent_delete(self, path):
        """Безвозвратное удаление"""
        try:
            if os.path.isfile(path):
                os.remove(path)
                return f"Файл удален: {path}"
            elif os.path.isdir(path):
                shutil.rmtree(path)
                return f"Папка удалена: {path}"
            else:
                return f"Путь не существует: {path}"
        except Exception as e:
            return f"Ошибка удаления: {e}"
    
    def ask_confirmation(self, message):
        """Запрос подтверждения через диалоговое окно"""
        # Создаем временное приложение для отображения диалога
        app = QApplication.instance() or QApplication(sys.argv)
        reply = QMessageBox.question(
            None,
            'Подтверждение',
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def handle_python(self, code):
        """Выполнение Python кода"""
        try:
            if not code:
                return "Введите код Python: py <код>"
            
            # Создаем отдельный контекст для выполнения
            local_context = {}
            
            # Выполняем код
            exec(code, self.python_context, local_context)
            
            # Если есть результат, возвращаем его
            if '_' in local_context:
                result = local_context['_']
                return str(result)
                
            return "Код выполнен"
        except Exception as e:
            return f"Ошибка выполнения Python кода: {e}"
    
    def handle_pip(self, args):
        """Выполнение команд pip"""
        try:
            # Получаем путь к pip
            pip_path = self.get_pip_path()
            if not pip_path:
                return "Не удалось найти pip. Убедитесь, что Python установлен правильно."
            
            # Формируем команду
            cmd = [pip_path] + args
            
            # Выполняем команду
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Возвращаем результат
            output = result.stdout or result.stderr
            return output if output else "Команда pip выполнена, но вывод отсутствует"
            
        except Exception as e:
            return f"Ошибка выполнения pip: {e}"
    
    def get_pip_path(self):
        """Поиск пути к pip"""
        # Попробуем найти pip в текущем окружении
        if hasattr(sys, 'base_prefix'):
            # Виртуальное окружение
            pip_path = os.path.join(sys.base_prefix, 'Scripts', 'pip.exe')
            if os.path.exists(pip_path):
                return pip_path
        
        # Проверим системный путь
        for path in os.environ['PATH'].split(os.pathsep):
            pip_path = os.path.join(path, 'pip.exe')
            if os.path.exists(pip_path):
                return pip_path
        
        # Последняя попытка: стандартное расположение
        pip_path = os.path.join(sys.prefix, 'Scripts', 'pip.exe')
        if os.path.exists(pip_path):
            return pip_path
        
        return None
    
    def handle_run(self, args):
        """Запуск программ по имени"""
        if not args:
            return "Использование: run <имя_программы>"
            
        program = args[0]
        # Проверяем зарегистрированные программы
        if program in self.programs:
            try:
                subprocess.Popen(self.programs[program], shell=True)
                return f"Программа '{program}' запущена"
            except Exception as e:
                return f"Ошибка запуска: {e}"
                
        # Попробуем найти в стандартных путях
        known_paths = {
            "cmd": "cmd.exe",
            "taskmgr": "taskmgr.exe",
            "resmon": "resmon.exe",
            "firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
            ],
            "firefox-nightly": [
                r"C:\Program Files\Firefox Nightly\firefox.exe",
                r"C:\Program Files (x86)\Firefox Nightly\firefox.exe"
            ],
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ],
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "discord": [
                r"C:\Users\{}\AppData\Local\Discord\app-1.0.9003\Discord.exe".format(os.getlogin()),
                r"C:\Program Files\Discord\Discord.exe"
            ],
            "steam": r"C:\Program Files (x86)\Steam\steam.exe",
            "spotify": [
                r"C:\Users\{}\AppData\Roaming\Spotify\Spotify.exe".format(os.getlogin()),
                r"C:\Program Files\WindowsApps\SpotifyAB.SpotifyMusic_1.180.612.0_x86__zpdnekdrzrea0\Spotify.exe"
            ],
            "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
            "pycharm": r"C:\Program Files\JetBrains\PyCharm Community Edition\bin\pycharm64.exe",
            "vscode": r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe".format(os.getlogin()),
            "itunes": r"C:\Program Files\iTunes\iTunes.exe",
            "7-zip": r"C:\Program Files\7-Zip\7zFM.exe",
            "winrar": r"C:\Program Files\WinRAR\WinRAR.exe"
        }
        
        if program in known_paths:
            paths = known_paths[program]
            if not isinstance(paths, list):
                paths = [paths]
            
            for path in paths:
                # Заменяем имя пользователя в пути
                if "{}" in path:
                    path = path.format(os.getlogin())
                
                if os.path.exists(path):
                    try:
                        subprocess.Popen([path])
                        return f"Программа '{program}' запущена"
                    except Exception as e:
                        return f"Ошибка запуска: {e}"
            
            return f"Программа '{program}' не установлена"
            
        return f"Неизвестная программа: {program}"
    
    def get_help(self):
        """Генерация текста справки"""
        help_text = "Доступные команды:\n"
        help_text += "  pacman list - Список установленных пакетов\n"
        help_text += "  pacman install <пакет> - Установка пакета\n"
        help_text += "  pacman delete <пакет>  - Удаление пакета\n"
        help_text += "  pacman reinstall <пакет> - Переустановка пакета\n"
        help_text += "  pacman update <пакет> - Обновление пакета\n"
        help_text += "  print <текст> - Вывод текста\n"
        help_text += "  start <программа> - Запуск программы\n"
        help_text += "  clear - Очистка экрана\n"
        help_text += "  help - Справка\n"
        help_text += "  exit - Выход\n"
        help_text += "  app install <приложение> - Установка приложений\n"
        help_text += "  app list - Список доступных приложений\n"
        help_text += "  rm [trb|nrb] <путь> - Удаление файлов/папок\n"
        help_text += "  py <код> - Выполнить Python код\n"
        help_text += "  python <код> - Выполнить Python код\n"
        help_text += "  pip <команда> - Выполнить команду pip\n"
        help_text += "  run <программа> - Запуск системных программ\n"
        
        if "TCMD" in self.packages:
            help_text += "  tcmd activate - Активировать TCMD эффекты\n"
            help_text += "  tcmd deactivate - Деактивировать TCMD эффекты\n"
            
        # Получение справки из установленных пакетов
        for package_name, package_module in self.loaded_packages.items():
            if hasattr(package_module, 'get_help'):
                package_help = package_module.get_help()
                if package_help:
                    help_text += f"\n{package_name} команды:\n{package_help}"
        
        return help_text


class TerminalWindow(QMainWindow):
    def __init__(self, cli):
        super().__init__()
        self.cli = cli
        self.cli.window = self  # Даём CLI доступ к окну
        self.setup_ui()
        self.setup_window()
        self.history = []
        self.history_index = -1
        self.drag_position = None
        
        # Таймер для перезапуска при активации TCMD
        self.restart_timer = QTimer(self)
        self.restart_timer.setSingleShot(True)
        self.restart_timer.timeout.connect(self.restart_application)
        
    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной макет
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Заголовок окна
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(30)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        
        self.title_label = QLabel("SqvPlasma Terminal")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        
        # Кнопки управления окном
        self.minimize_btn = QLabel("−")
        self.minimize_btn.setStyleSheet("color: white; font-size: 20px; padding: 0 10px;")
        self.minimize_btn.mousePressEvent = lambda e: self.showMinimized()
        
        self.close_btn = QLabel("×")
        self.close_btn.setStyleSheet("color: white; font-size: 20px; padding: 0 10px;")
        self.close_btn.mousePressEvent = lambda e: self.close()
        
        title_layout.addWidget(self.minimize_btn)
        title_layout.addWidget(self.close_btn)
        
        main_layout.addWidget(self.title_bar)
        
        # Область вывода
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QFont("Consolas", 10))
        main_layout.addWidget(self.output_area, 1)
        
        # Поле ввода
        self.input_field = QLineEdit()
        self.input_field.setFont(QFont("Consolas", 10))
        self.input_field.returnPressed.connect(self.execute_command)
        self.input_field.setFocus()
        
        main_layout.addWidget(self.input_field)
        
        # Применение темы
        self.apply_custom_theme(self.cli.config.get("theme", "dark"))
        
        # Приветственное сообщение
        self.output_area.append("Добро пожаловать в SqvPlasma Terminal!")
        self.output_area.append("Введите 'help' для списка команд")
        
        if self.cli.config.get("tcmd_active", False):
            self.output_area.append(">> TCMD эффекты активны <<")
        
    def setup_window(self):
        """Настройка свойств окна"""
        # Borderless окно
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Фиксированный размер 800x600
        self.setFixedSize(800, 600)
        
        # Центрирование окна
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        # Применение эффектов TCMD
        if self.cli.config.get("tcmd_active", False):
            self.apply_tcmd_effects()
        
    def apply_tcmd_effects(self):
        """Применение эффектов TCMD"""
        # Полупрозрачность
        self.setWindowOpacity(0.9)
        
        # Красная граница
        self.repaint()
        
    def paintEvent(self, event):
        """Рисование красной границы при активном TCMD"""
        super().paintEvent(event)
        
        if self.cli.config.get("tcmd_active", False):
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.drawRect(0, 0, self.width(), self.height())
    
    def mousePressEvent(self, event):
        """Перетаскивание окна"""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
            
    def mouseMoveEvent(self, event):
        """Перетаскивание окна"""
        if hasattr(self, 'old_pos') and event.buttons() & Qt.LeftButton:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
    
    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        self.old_pos = None
    
    def execute_command(self):
        command = self.input_field.text().strip()
        self.input_field.clear()
        
        if not command:
            return
            
        self.history.append(command)
        self.history_index = len(self.history)
        
        self.output_area.append(f"> {command}")
        
        # Выполнение команды
        result = self.cli.execute_command(command)
        
        # Обработка специальных команд
        if result == "clear":
            self.output_area.clear()
        elif command.startswith("theme "):
            theme = command.split(" ", 1)[1]
            self.apply_custom_theme(theme)
            self.output_area.append(f"Тема изменена на: {theme}")
        elif command.startswith("font "):
            try:
                size = int(command.split(" ", 1)[1])
                font = self.output_area.font()
                font.setPointSize(size)
                self.output_area.setFont(font)
                self.input_field.setFont(font)
                self.output_area.append(f"Размер шрифта изменен на: {size}")
            except:
                self.output_area.append("Некорректный размер шрифта")
        elif command.startswith("color "):
            try:
                color = command.split(" ", 1)[1]
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(color))
                self.output_area.mergeCurrentCharFormat(fmt)
                self.output_area.append(f"Цвет текста изменен на: {color}")
            except:
                self.output_area.append("Некорректный цвет")
        elif result:
            self.output_area.append(result)
            
        # Проверка на перезапуск
        if "перезапуск приложения" in str(result):
            self.restart_timer.start(1000)
            
        # Прокрутка вниз
        self.output_area.verticalScrollBar().setValue(
            self.output_area.verticalScrollBar().maximum()
        )
    
    def keyPressEvent(self, event):
        """Навигация по истории команд"""
        if event.key() == Qt.Key_Up:
            if self.history:
                self.history_index = max(0, self.history_index - 1)
                self.input_field.setText(self.history[self.history_index])
                
        elif event.key() == Qt.Key_Down:
            if self.history:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.input_field.setText(self.history[self.history_index])
                else:
                    self.history_index = len(self.history)
                    self.input_field.clear()
        else:
            super().keyPressEvent(event)
    
    def restart_application(self):
        """Перезапуск приложения"""
        try:
            # Получаем путь к текущему интерпретатору Python
            python = sys.executable
            
            # Формируем команду для запуска нового процесса
            cmd = [python, os.path.abspath(sys.argv[0])]
            
            # Запускаем новый процесс
            subprocess.Popen(cmd, cwd=os.getcwd())
            
            # Закрываем текущее приложение
            QApplication.quit()
            
        except Exception as e:
            self.output_area.append(f"Ошибка перезапуска: {e}")
    
    def apply_custom_theme(self, theme_name):
        """Применение пользовательской темы"""
        if theme_name == "dark":
            self.apply_dark_theme()
        elif theme_name == "light":
            self.apply_light_theme()
        else:
            self.output_area.append(f"Неизвестная тема: {theme_name}. Доступные: dark, light")
    
    def apply_dark_theme(self):
        """Темная тема"""
        self.output_area.setStyleSheet("""
            QTextEdit {
                background-color: #1e272e;
                color: #ecf0f1;
                border: none;
                padding: 10px;
            }
        """)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: none;
                padding: 10px;
                border-top: 1px solid #34495e;
            }
        """)
        self.title_bar.setStyleSheet("background-color: #2c3e50;")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.minimize_btn.setStyleSheet("color: white; font-size: 20px; padding: 0 10px;")
        self.close_btn.setStyleSheet("color: white; font-size: 20px; padding: 0 10px;")
        self.cli.config["theme"] = "dark"
        self.cli.save_data(self.cli.config, CONFIG_FILE)
    
    def apply_light_theme(self):
        """Светлая тема"""
        self.output_area.setStyleSheet("""
            QTextEdit {
                background-color: #f5f6fa;
                color: #2f3640;
                border: none;
                padding: 10px;
            }
        """)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #dcdde1;
                color: #2f3640;
                border: none;
                padding: 10px;
                border-top: 1px solid #7f8fa6;
            }
        """)
        self.title_bar.setStyleSheet("background-color: #718093;")
        self.title_label.setStyleSheet("color: black; font-weight: bold;")
        self.minimize_btn.setStyleSheet("color: black; font-size: 20px; padding: 0 10px;")
        self.close_btn.setStyleSheet("color: black; font-size: 20px; padding: 0 10px;")
        self.cli.config["theme"] = "light"
        self.cli.save_data(self.cli.config, CONFIG_FILE)


def main():
    # Инициализация CLI
    cli = CommandLine()
    
    # Создание приложения
    app = QApplication(sys.argv)
    
    # Создание и отображение окна
    window = TerminalWindow(cli)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()