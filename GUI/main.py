"""
UltraBike GUI - Entry Point
Just launches the app, nothing else
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from GUI.app import UltraBikeApp

def main(page: ft.Page):
    UltraBikeApp(page)

if __name__ == "__main__":
    ft.app(target=main)