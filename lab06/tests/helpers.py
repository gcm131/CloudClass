"""Helpers shared by integration and chaos tests."""
import socket
import time
import requests

def get_json(url: str, timeout: float = 15.0) -> tuple[int, dict | str]:
    try:
        resp = requests.get(url, timeout=timeout)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text
    except requests.RequestException as err:
        return 0, {"error": str(err)}

def wait_until(check, timeout: int = 360, interval: int = 10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = check()
        if res:
            return res
        time.sleep(interval)
    return None

def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False