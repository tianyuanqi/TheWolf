"""单SQLite的事实、发布与原件边界；不提供旧存储回退。"""
from .database import Database, StorageError

__all__ = ['Database', 'StorageError']
