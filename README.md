# 🚀 vnStat Web Dashboard

Лёгкий веб-дашборд для мониторинга сетевого трафика через **vnStat**

Скрипт подключается к удалённым серверам по SSH, собирает данные vnStat в формате JSON и отображает их в удобном современном интерфейсе с графиками. Поддерживает несколько серверов, авторизацию и автоматическое обновление данных

---

## ✨ Возможности

* 📡 Сбор данных с удалённых серверов по SSH
* 📊 Визуализация трафика (день / месяц) с помощью Chart.js
* 🔄 Автоматическое обновление данных
* 🔐 Простая авторизация
* 🖥 Поддержка нескольких серверов

---

## 🛠 Требования

* Python 3.9+
* Установленный на хостах vnStat 
* Доступ по SSH

---

## 📦 Установка

```bash
apt install vnstat
curl -L https://github.com/md3xf4ck/vnStat-web-dashboard/releases/latest/download/vnStat-web-dashboard.zip -o vnstat-web-dashboard.zip
unzip vnstat-web-dashboard.zip
cd vnStat-web-dashboard
pip install -r requirements.txt
```

---

## ⚙️ Настройка

Отредактируйте `config.py`:

```python
CONFIG = {
    "auth": {
        "username": "admin",
        "password": "changeme",
    },
    "secret_key": "your-secret-key",
    "refresh_interval": 60,
    "servers": {
        "server1": {
            "host": "1.2.3.4",
            "port": 22,
            "user": "root",
            "password": "password",
            # или используйте ключ:
            # "key_path": "/path/to/key",
            "interface": "eth0"
        }
    },
}
```

---

## ▶️ Запуск

```bash
python app.py
```

Приложение будет доступно по адресу:

```
http://localhost:3232
```

---

## 🔐 Авторизация

Используйте логин и пароль из `config.py`:

```python
"auth": {
    "username": "admin",
    "password": "changeme"
}
```

---

## 📡 Как это работает

1. Приложение подключается к серверу через SSH
2. Выполняет команду:

   ```bash
   vnstat --json
   ```
3. Парсит данные
4. Кэширует результат
5. Отображает в веб-интерфейсе

---

## 🧠 Кэширование

* Данные обновляются каждые `refresh_interval` секунд
* Потокобезопасность обеспечивается через `threading.Lock`

---

## ⚠️ Безопасность

Рекомендуется:

* Использовать SSH-ключи вместо пароля
* Задать сложный `secret_key`
* Не использовать дефолтные логин/пароль

---

## 🔧 Зависимости

* Flask
* paramiko
* Chart.js (через CDN)

---

## 📌 TODO

* Поддержка Docker
* Темная/светлая тема
* Автовыдача SSL сертификатов Lets Encrypt

---

## 📄 Лицензия

MIT License
