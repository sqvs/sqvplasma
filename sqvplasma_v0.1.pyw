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
from PyQt5.QtCore import Qt, QPoint, QTimer, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QTextCursor, QTextCharFormat

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

# Класс для отслеживания установщиков
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
        for package_name in self.packages:
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
            print(f"ошибка загрузки пакета {package_name}: {e}")
    
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
        if cmd == "pacman" and len(args) >= 1:
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
            return "Использование: pacman [install|delete|reinstall|update|list] <пакет>"
            
        action = args[0]
        
        if action == "list":
            if not self.packages:
                return "Нет установленных пакетов"
            return "\n".join([f"{pkg}: {info['version']}" for pkg, info in self.packages.items()])
        
        if len(args) < 2:
            return f"Для действия {action} требуется указать пакет"
            
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
        """Управление приложениями"""
        if not args:
            return "Использование: app [install|list] <название_приложения>"
            
        action = args[0].lower()
        
        if action == "list":
            apps = self.get_application_list()
            return "\n".join(apps)
            
        elif action == "install" and len(args) >= 2:
            app_name = args[1].lower()
            return self.install_application(app_name)
            
        return f"Неизвестная команда app: {' '.join(args)}"
    
    def get_application_list(self):
        """Получение списка доступных приложений"""
        categories = {
            "VPN сервисы": ["expressvpn", "nordvpn", "surfshark", "cyberghostvpn", "protonvpn"],
            "Медиаплееры и стриминги": ["spotify", "itunes", "vlc", "winamp", "aimp"],
            "Торрент-клиенты": ["qbittorrent", "deluge", "utorrent", "bittorrent"],
            "Мессенджеры": ["whatsapp", "signal", "telegram", "discord"],
            "Инструменты разработчика": ["pycharm", "intellij", "androidstudio", "git"],
            "Игровые платформы": ["epicgames", "origin", "battlenet", "steam"],
            "Системные утилиты": ["ccleaner", "regOrganizer (Maybe virus, download only at ur risk. Check the link of it in source code if u want.)", "winrar", "7zip"],
            "Офисные приложения": ["libreoffice", "openoffice", "acrobatreader"],
            "Другие полезные приложения": ["teamviewer", "zoom", "skype", "notepadplusplus"]
        }
        
        result = ["Доступные приложения:"]
        for category, apps in categories.items():
            result.append(f"\n{category}:")
            result.extend([f"  - {app}" for app in apps])
            
        return result
    
    def install_application(self, app_name):
        """Установка указанного приложения"""
        # Список поддерживаемых приложений и их URL
        applications = {
            # VPN сервисы
            "expressvpn": "https://www.expressvpn.works/clients/windows/expressvpn_setup.exe",
            "nordvpn": "https://downloads.nordcdn.com/apps/windows/NordVPNSetup.exe",
            "surfshark": "https://downloads.surfshark.com/windows/client/win-stable/install.exe",
            "cyberghostvpn": "https://download.cyberghostvpn.com/installation_files/setup.exe",
            "protonvpn": "https://protonvpn.com/download/ProtonVPN_win_v3.4.1.exe",
            "planetvpn": "https://cdn.planetvpn.cloud/win/planetvpn.exe",
            
            # Медиаплееры и стриминги
            "spotify": "https://download.scdn.co/SpotifySetup.exe",
            "itunes": "https://www.apple.com/itunes/download/win64",
            "vlc": "https://get.videolan.org/vlc/3.0.18/win64/vlc-3.0.18-win64.exe",
            "winamp": "https://download.nullsoft.com/winamp/winamp5666_full_all.exe",
            "aimp": "https://www.aimp.ru/?do=download.file&id=26",
            
            # Торрент-клиенты
            "qbittorrent": "https://www.fosshub.com/qBittorrent.html?dwl=qbittorrent_4.5.5_x64_setup.exe",
            "deluge": "https://ftp.osuosl.org/pub/deluge/windows/deluge-2.1.1-win64-py3.11.exe",
            "utorrent": "https://download.utorrent.com/utorrent/utorrent.exe",
            "bittorrent": "https://download-new.utorrent.com/endpoint/bittorrent/os/windows/track/stable",
            
            # Мессенджеры
            "whatsapp": "https://web.whatsapp.com/desktop/windows/release/x64/WhatsAppSetup.exe",
            "signal": "https://updates.signal.org/desktop/signal-desktop-win-6.39.0.exe",
            "telegram": "https://telegram.org/dl/desktop/win",
            "discord": "https://discord.com/api/downloads/distributions/app/installers/latest?channel=stable&platform=win&arch=x86",
            
            # Инструменты разработчика
            "pycharm": "https://download.jetbrains.com/python/pycharm-professional-2023.2.3.exe",
            "intellij": "https://download.jetbrains.com/idea/ideaIU-2023.2.4.exe",
            "androidstudio": "https://redirector.gvt1.com/edgedl/android/studio/install/2022.2.1.20/android-studio-2022.2.1.20-windows.exe",
            "git": "https://github.com/git-for-windows/git/releases/download/v2.42.0.windows.2/Git-2.42.0.2-64-bit.exe",
            
            # Игровые платформы
            "epicgames": "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi",
            "origin": "https://origin-a.akamaihd.net/Origin-Client-Download/origin/live/OriginSetup.exe",
            "battlenet": "https://www.battle.net/download/getInstallerForGame?os=win&gameProgram=BATTLENET_APP&version=Live",
            "steam": "https://cdn.cloudflare.steamstatic.com/client/installer/SteamSetup.exe",
            
            # Системные утилиты
            "ccleaner": "https://download.ccleaner.com/ccsetup615.exe",
            "regorganizer": "https://regorganizer.ru/download/regorganizer.zip",
            "winrar": "https://www.win-rar.com/fileadmin/winrar-versions/winrar/winrar-x64-624.exe",
            "7zip": "https://www.7-zip.org/a/7z2400-x64.exe",
            
            # Офисные приложения
            "libreoffice": "https://download.documentfoundation.org/libreoffice/stable/7.6.4/win/x86_64/LibreOffice_7.6.4_Win_x86-64.msi",
            "openoffice": "https://sourceforge.net/projects/openofficeorg.mirror/files/4.1.14/binaries/en-US/Apache_OpenOffice_4.1.14_Win_x86_install_en-US.exe",
            "acrobatreader": "https://ardownload2.adobe.com/pub/adobe/reader/win/AcrobatDC/2300820243/AcroRdrDC2300820243_en_US.exe",
            
            # Другие полезные приложения
            "teamviewer": "https://download.teamviewer.com/download/TeamViewer_Setup.exe",
            "zoom": "https://cdn.zoom.us/prod/5.16.1.25216/ZoomInstaller.exe",
            "skype": "https://download.skype.com/s4l/download/win/Skype-8.104.0.209.exe",
            "notepadplusplus": "https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.5.6/npp.8.5.6.Installer.x64.exe"
        }
        
        if app_name not in applications:
            return f"Приложение '{app_name}' не поддерживается. Введите 'app list' для списка приложений."
            
        # Запрос подтверждения
        confirm = self.ask_confirmation(f"Вы уверены, что хотите установить {app_name}?")
        if not confirm:
            return "Установка отменена"
            
        # Скачивание установщика
        url = applications[app_name]
        try:
            # Для некоторых приложений требуется специальная обработка
            if app_name == "telegram":
                webbrowser.open(url)
                return f"Установщик Telegram будет скачан в браузере. Завершите установку вручную."
                
            if app_name in ["epicgames", "acrobatreader", "libreoffice"]:
                # Для MSI и специальных установщиков
                webbrowser.open(url)
                return f"Установщик {app_name} будет скачан в браузере. Завершите установку вручную."
                
            # Скачиваем установщик
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Определяем имя файла
            if "content-disposition" in response.headers:
                content_disposition = response.headers["content-disposition"]
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[1].strip('"')
                else:
                    filename = f"{app_name}_installer.exe"
            else:
                # Попробуем извлечь имя файла из URL
                if "/" in url:
                    filename = url.split("/")[-1]
                else:
                    filename = f"{app_name}_installer.exe"
            
            # Убираем параметры запроса из имени файла
            if "?" in filename:
                filename = filename.split("?")[0]
            
            # Сохраняем файл
            installer_path = os.path.abspath(filename)
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # фильтруем keep-alive новые чанки
                        f.write(chunk)
            
            # Запускаем установщик
            process = subprocess.Popen([installer_path], shell=True)
            
            # Создаем и запускаем трекер для отслеживания завершения установки
            tracker = InstallerTracker(process, app_name, installer_path)
            tracker.finished.connect(self.on_installer_finished)
            tracker.start()
            
            return f"Установщик {app_name} скоро будет запущен. После завершения установки вам будет предложено удалить установщик."
            
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
            return "Использование: rm [trb | nrb] <путь>"
            
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
    
    def get_help(self):
        """Генерация текста справки"""
        help_text = "Доступные команды:\n"
        help_text += "  pacman install <пакет> - Установка пакета\n"
        help_text += "  pacman delete <пакет>  - Удаление пакета\n"
        help_text += "  pacman reinstall <пакет> - Переустановка пакета\n"
        help_text += "  pacman update <пакет> - Обновление пакета\n"
        help_text += "  pacman list - Список установленных пакетов\n"
        help_text += "  print <текст> - Вывод текста\n"
        help_text += "  start <программа> - Запуск программы\n"
        help_text += "  clear - Очистка экрана\n"
        help_text += "  help - Справка\n"
        help_text += "  exit - Выход\n"
        help_text += "  app install <приложение> - Установка приложений\n"
        help_text += "  app list - Список доступных приложений\n"
        help_text += "  rm trb <путь> - Удаление в корзину\n"
        help_text += "  rm nrb <путь> - Безвозвратное удаление\n"
        help_text += "  py <код> - Выполнить Python код\n"
        help_text += "  python <код> - Выполнить Python код\n"
        help_text += "  pip <команда> - Выполнить команду pip\n"
        
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
        screen = QApplication.primaryScreen().availableGeometry()
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
            self.drag_position = event.globalPos()
            
    def mouseMoveEvent(self, event):
        """Перетаскивание окна"""
        if self.drag_position and event.buttons() & Qt.LeftButton:
            delta = QPoint(event.globalPos() - self.drag_position)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.drag_position = event.globalPos()
    
    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        self.drag_position = None
    
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