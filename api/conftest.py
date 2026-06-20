"""pytest がリポジトリ直下や api/ どちらから実行されても api パッケージを
解決できるようにする。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
