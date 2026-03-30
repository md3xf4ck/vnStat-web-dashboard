CONFIG = {
    "auth": {
        "username": "admin",
        "password": "changeme",
    },
    "secret_key": "changeme",
    "refresh_interval": 60,
    "servers": {
        "name of your server": {
            "host": "ip of your server",
            "port": 22,
            "user": "",
            "password": "", # or comment it and use key_path
            #"key_path": "/path/to/your/ssh/key",
            "interface": "eth0"
        },
        "server2": {
            "host": "ip",
            "port": 22,
            "user": "root",
            "password": "password",
            "interface": "ens3"
        }
    },
}