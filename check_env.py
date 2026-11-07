#!/usr/bin/env python3
"""Teste T0 - verifica o ambiente antes de tentar conectar a uma live.

Usa apenas a biblioteca padrão do Python (funciona antes do pip install).
  python check_env.py
  python check_env.py --sign-url http://127.0.0.1:8080
"""
import argparse
import platform
import socket
import sys
import urllib.error
import urllib.request


def http_check(label: str, url: str, timeout: float = 10.0) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "souza-live-spike/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            print(f"  [OK]    {label}: HTTP {r.status} ({url})")
            return True
    except urllib.error.HTTPError as e:
        # Um erro HTTP (403, 404...) ainda prova que o servidor respondeu.
        print(f"  [RESP]  {label}: o servidor respondeu HTTP {e.code} ({url})")
        return True
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        print(f"  [FALHA] {label}: {type(e).__name__}: {e} ({url})")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sign-url", default=None, help="servidor de assinatura próprio a testar (opcional)")
    args = ap.parse_args()

    print("== Ambiente ==")
    print(f"  Python: {sys.version.split()[0]}  ({platform.platform()})")
    if sys.version_info < (3, 10):
        print("  [ATENCAO] Python abaixo de 3.10. Instale 3.11 ou 3.12.")

    print("== Biblioteca ==")
    try:
        import importlib.metadata as md
        print(f"  TikTokLive instalada: versão {md.version('TikTokLive')}")
    except Exception:
        print("  TikTokLive NÃO instalada (rode: pip install -r requirements.txt)")

    print("== Rede ==")
    ok_tt = http_check("TikTok (site)", "https://www.tiktok.com/")
    if args.sign_url:
        base = args.sign_url.rstrip("/")
        http_check("Servidor de assinatura (raiz)", base + "/")
        http_check("Servidor de assinatura (/healthz)", base + "/healthz")
    else:
        print("  (nenhum --sign-url informado: será usado o padrão da biblioteca no teste T1)")

    print("\nCopie TODA esta saída e envie junto com os resultados.")
    return 0 if ok_tt else 1


if __name__ == "__main__":
    sys.exit(main())
